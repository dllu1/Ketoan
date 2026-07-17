"""Service for the raw-material NXT worksheet (Bảng kê N–X–T NVL chính).

The worksheet is two-way linked with the live inventory ledger so the Kho hàng
tabs stay consistent (yêu cầu: vật tư trên bảng kê phải xuất hiện ở Nhập–Xuất–Tồn
và ngược lại):

* **Sổ kho → bảng kê (đọc):** materials that already have *real* document
  movements (mua hàng / bán hàng / nhập kho) are pulled in as read-only rows,
  computed straight from the ledger for the period and flagged ``from_ledger``
  so the UI greys them and :meth:`save` never re-pushes them.

* **Bảng kê → sổ kho (ghi):** the remaining *manual* materials (no real
  movement — vd: NVL theo dõi tay) are persisted to ``material_sheet_line`` *and*
  pushed into the ledger under a per-period source key ``BK-NVL:<period>`` so
  they show up in Nhập–Xuất–Tồn (and every other ledger-derived report) without
  double-counting real chứng từ.

The negative-closing guard (tồn cuối kỳ < 0 ⇒ không lưu) still applies, but only
to the manual rows the worksheet actually owns.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from data.repositories.inventory_repo import InventoryRepository
from data.repositories.item_repo import ItemRepository
from domain.models.inventory import InventoryMovement, MovementKind, NxtRow
from domain.models.material_sheet import MaterialLine, MaterialSheet
from domain.services.inventory_service import InventoryService

_SHEET_SOURCE_PREFIX = "BK-NVL:"     # source tag for worksheet-pushed movements
_COSTING_SOURCE_PREFIX = "GT-NVL:"   # xuất NVL theo giá thành (do bảng giá thành đẩy)
_MATERIAL_ACCOUNT = "152"            # nhóm Nguyên vật liệu (TT200)
_ZERO = Decimal("0")
_ONE = Decimal("1")


class MaterialSheetError(ValueError):
    pass


def _period_bounds(period_key: str) -> tuple[date, date]:
    """[start, end] dates for a worksheet period_key ('2026' or '2026-06')."""
    parts = period_key.split("-")
    year = int(parts[0])
    if len(parts) == 1:
        return date(year, 1, 1), date(year, 12, 31)
    month = int(parts[1])
    start = date(year, month, 1)
    end = (date(year, 12, 31) if month == 12
           else date(year, month + 1, 1) - timedelta(days=1))
    return start, end


def _unit_cost(value: Decimal, qty: Decimal) -> Decimal:
    return (value / qty).quantize(_ONE) if qty else _ZERO


class MaterialSheetService:
    def __init__(
        self,
        repo,
        inventory: InventoryService | None = None,
        item_repo: ItemRepository | None = None,
    ) -> None:
        self._repo = repo
        self._inventory = inventory or InventoryService(
            InventoryRepository(), ItemRepository()
        )
        self._items = item_repo or ItemRepository()

    # ----- load: ledger materials (read-only) + manual rows ----------------

    def load(self, period_key: str) -> MaterialSheet:
        ledger_lines = [
            self._nxt_to_line(r) for r in self._ledger_material_rows(period_key)
        ]
        ledger_codes = {line.code for line in ledger_lines}
        manual = [
            line for line in self._repo.list_for_period(period_key)
            if line.code.strip() not in ledger_codes
        ]
        return MaterialSheet(period_key=period_key, lines=ledger_lines + manual)

    # ----- save: persist + push only the rows the worksheet owns -----------

    def validate(self, sheet: MaterialSheet) -> list[MaterialLine]:
        """Negative-closing rows the worksheet *owns* (ledger rows excluded)."""
        return [line for line in self._manual_lines(sheet) if line.is_negative]

    def save(self, sheet: MaterialSheet) -> None:
        offending = self.validate(sheet)
        if offending:
            names = ", ".join(line.code or line.name or "?" for line in offending)
            raise MaterialSheetError(
                "Không thể lưu: tồn cuối kỳ không được âm. "
                f"Kiểm tra lại các vật tư: {names}."
            )
        manual = self._manual_lines(sheet)
        self._repo.replace(sheet.period_key, manual)
        self._push_to_ledger(sheet.period_key, manual)

    # ----- internals -------------------------------------------------------

    def _manual_lines(self, sheet: MaterialSheet) -> list[MaterialLine]:
        """Non-empty rows the worksheet owns: not ledger-derived, and not the
        code of a material already driven by real document movements."""
        ledger_codes = {
            r.item_code for r in self._ledger_material_rows(sheet.period_key)
        }
        return [
            line for line in sheet.lines
            if not line.is_empty
            and not line.from_ledger
            and line.code.strip() not in ledger_codes
        ]

    def _ledger_material_rows(self, period_key: str) -> list[NxtRow]:
        """Real (non-worksheet) NXT rows for nhóm 152 within the period.

        Excludes both the sheet's own push (BK-NVL) and the costing issue
        (GT-NVL): the latter is production consumption shown in the NXT report,
        not something this worksheet owns — leaking it in would strand a phantom
        xuất row for hand-tracked materials.
        """
        start, end = _period_bounds(period_key)
        rows = self._inventory.compute_nxt(
            start, end,
            exclude_source_prefix=(_SHEET_SOURCE_PREFIX, _COSTING_SOURCE_PREFIX),
        )
        return [
            r for r in rows
            if r.account_code == _MATERIAL_ACCOUNT
            and any((r.opening_qty, r.in_qty, r.out_qty,
                     r.opening_value, r.in_value, r.out_value))
        ]

    @staticmethod
    def _nxt_to_line(r: NxtRow) -> MaterialLine:
        return MaterialLine(
            code=r.item_code, name=r.item_name, unit=r.unit,
            opening_price=_unit_cost(r.opening_value, r.opening_qty),
            opening_qty=r.opening_qty, opening_value=r.opening_value,
            in_price=_unit_cost(r.in_value, r.in_qty),
            in_qty=r.in_qty, in_value=r.in_value,
            out_price=_unit_cost(r.out_value, r.out_qty),
            out_qty=r.out_qty, out_value=r.out_value,
            from_ledger=True,
        )

    def _push_to_ledger(self, period_key: str, manual: list[MaterialLine]) -> None:
        source = _SHEET_SOURCE_PREFIX + period_key
        start, _ = _period_bounds(period_key)
        opening_date = start - timedelta(days=1)   # so it counts as đầu kỳ in NXT
        now = datetime.now()
        movements: list[InventoryMovement] = []
        for line in manual:
            item = self._items.find_by_code(line.code)
            name = line.name or (item.name if item else "")
            account = (item.account_code if item else "") or _MATERIAL_ACCOUNT
            specs = (
                (MovementKind.OPENING, opening_date, line.opening_qty, line.opening_value),
                (MovementKind.IN, start, line.in_qty, line.in_value),
                (MovementKind.OUT, start, line.out_qty, line.out_value),
            )
            for kind, when, qty, value in specs:
                if qty <= _ZERO:
                    continue
                movements.append(InventoryMovement(
                    item_code=line.code, item_name=name, account_code=account,
                    move_date=when, kind=kind, quantity=qty,
                    unit_cost=_unit_cost(value, qty), source_ref=source,
                    note="Bảng kê NVL chính", created_at=now,
                ))
        self._inventory.replace_source_movements(source, movements)
