"""Service for the finished-goods NXT worksheet (Bảng kê N–X–T thành phẩm, 155).

Follows the same two-way ledger link as the NVL sheet so the Kho hàng tabs stay
consistent and never double-count:

* **Sổ kho → bảng kê (đọc):** products with *real* document movements (vd: hóa
  đơn bán hàng xuất 155, nhập kho TP) come in as read-only rows flagged
  ``from_ledger``; :meth:`save` never re-pushes them.
* **Bảng kê → sổ kho (ghi):** manual rows are persisted to
  ``product_sheet_line`` *and* pushed into the ledger under the per-period
  source key ``BK-TP:<period>`` so they appear in Nhập–Xuất–Tồn.

On top of that, the form rules specific to thành phẩm:

* **Carry-forward:** opening a period with no saved sheet pre-fills tồn đầu kỳ
  from the previous period's manual closing balances (tồn đầu tháng này =
  tồn cuối tháng trước).
* **Nhập từ giá thành:** :meth:`apply_costing` fills SL nhập / TT nhập from the
  period's costing sheet (SL = quantity produced, TT = tổng giá thành).
* Manual rows always re-derive ĐG xuất bình quân gia quyền via
  :meth:`ProductLine.recompute` before display and save.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from data.repositories.costing_repo import CostingRepository
from data.repositories.inventory_repo import InventoryRepository
from data.repositories.item_repo import ItemRepository
from domain.models.inventory import InventoryMovement, MovementKind, NxtRow
from domain.models.product_sheet import ProductLine, ProductSheet
from domain.services.costing_service import CostingService
from domain.services.inventory_service import InventoryService
from domain.services.material_sheet_service import _period_bounds, _unit_cost

_SHEET_SOURCE_PREFIX = "BK-TP:"      # source tag for worksheet-pushed movements
_PRODUCT_ACCOUNT = "155"             # nhóm Thành phẩm (TT200)
_ZERO = Decimal("0")


class ProductSheetError(ValueError):
    pass


def previous_period_key(period_key: str) -> str:
    """'2026' → '2025'; '2026-06' → '2026-05'; '2026-01' → '2025-12'."""
    parts = period_key.split("-")
    year = int(parts[0])
    if len(parts) == 1:
        return str(year - 1)
    month = int(parts[1])
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


class ProductSheetService:
    def __init__(
        self,
        repo,
        inventory: InventoryService | None = None,
        item_repo: ItemRepository | None = None,
        costing: CostingService | None = None,
    ) -> None:
        self._repo = repo
        self._inventory = inventory or InventoryService(
            InventoryRepository(), ItemRepository()
        )
        self._items = item_repo or ItemRepository()
        self._costing = costing or CostingService(CostingRepository())

    # ----- load: ledger rows (read-only) + manual rows + carry-forward ------

    def load(self, period_key: str) -> ProductSheet:
        ledger_lines = [
            self._nxt_to_line(r) for r in self._ledger_product_rows(period_key)
        ]
        ledger_codes = {line.code for line in ledger_lines}
        saved = self._repo.list_for_period(period_key)
        if saved:
            manual = [ln for ln in saved if ln.code.strip() not in ledger_codes]
        else:
            # First open of this period: tồn đầu kỳ = tồn cuối kỳ trước.
            manual = [
                ln for ln in self.carry_forward_lines(period_key)
                if ln.code.strip() not in ledger_codes
            ]
        for line in manual:
            line.recompute()
        return ProductSheet(period_key=period_key, lines=ledger_lines + manual)

    def carry_forward_lines(self, period_key: str) -> list[ProductLine]:
        """Openings for *period_key* built from the previous period's closings."""
        carried: list[ProductLine] = []
        for prev in self._repo.list_for_period(previous_period_key(period_key)):
            prev.recompute()
            if prev.closing_qty == _ZERO and prev.closing_value == _ZERO:
                continue
            carried.append(ProductLine(
                code=prev.code, name=prev.name, unit=prev.unit,
                opening_price=prev.closing_price,
                opening_qty=prev.closing_qty,
                opening_value=prev.closing_value,
            ))
        return carried

    # ----- costing pull ------------------------------------------------------

    def apply_costing(self, sheet: ProductSheet) -> int:
        """Fill SL nhập / TT nhập from the period's costing sheet (giá thành).

        Returns how many products were filled. Products already driven by real
        ledger movements are skipped (their nhập comes from chứng từ). Costing
        rows without a matching worksheet row are appended as new lines.
        """
        costing = self._costing.load(sheet.period_key)
        ledger_codes = {ln.code for ln in sheet.lines if ln.from_ledger}
        by_code = {
            ln.code: ln for ln in sheet.lines
            if not ln.from_ledger and ln.code.strip()
        }
        applied = 0
        for row in costing.rows:
            code = row.code.strip()
            if not code or row.quantity <= _ZERO or code in ledger_codes:
                continue
            line = by_code.get(code)
            if line is None:
                item = self._items.find_by_code(code)
                line = ProductLine(
                    code=code,
                    name=row.name or (item.name if item else ""),
                    unit=item.unit if item else "",
                )
                sheet.lines.append(line)
                by_code[code] = line
            line.in_qty = row.quantity
            line.in_value = row.total_cost
            line.recompute()
            applied += 1
        return applied

    # ----- save: guard + persist + push only the rows the sheet owns --------

    def validate(self, sheet: ProductSheet) -> list[ProductLine]:
        """Negative-closing rows the worksheet *owns* (ledger rows excluded)."""
        return [line for line in self._manual_lines(sheet) if line.is_negative]

    def save(self, sheet: ProductSheet) -> None:
        manual = self._manual_lines(sheet)
        for line in manual:
            line.recompute()
        offending = [line for line in manual if line.is_negative]
        if offending:
            names = ", ".join(line.code or line.name or "?" for line in offending)
            raise ProductSheetError(
                "Không thể lưu: tồn cuối kỳ không được âm. "
                f"Kiểm tra lại các thành phẩm: {names}."
            )
        self._repo.replace(sheet.period_key, manual)
        self._push_to_ledger(sheet.period_key, manual)

    # ----- internals ---------------------------------------------------------

    def _manual_lines(self, sheet: ProductSheet) -> list[ProductLine]:
        ledger_codes = {
            r.item_code for r in self._ledger_product_rows(sheet.period_key)
        }
        return [
            line for line in sheet.lines
            if not line.is_empty
            and not line.from_ledger
            and line.code.strip() not in ledger_codes
        ]

    def _ledger_product_rows(self, period_key: str) -> list[NxtRow]:
        """Real (non-worksheet) NXT rows for nhóm 155 within the period."""
        start, end = _period_bounds(period_key)
        rows = self._inventory.compute_nxt(
            start, end, exclude_source_prefix=_SHEET_SOURCE_PREFIX
        )
        return [
            r for r in rows
            if r.account_code == _PRODUCT_ACCOUNT
            and any((r.opening_qty, r.in_qty, r.out_qty,
                     r.opening_value, r.in_value, r.out_value))
        ]

    @staticmethod
    def _nxt_to_line(r: NxtRow) -> ProductLine:
        return ProductLine(
            code=r.item_code, name=r.item_name, unit=r.unit,
            opening_price=_unit_cost(r.opening_value, r.opening_qty),
            opening_qty=r.opening_qty, opening_value=r.opening_value,
            in_price=_unit_cost(r.in_value, r.in_qty),
            in_qty=r.in_qty, in_value=r.in_value,
            out_price=_unit_cost(r.out_value, r.out_qty),
            out_qty=r.out_qty, out_value=r.out_value,
            from_ledger=True,
        )

    def _push_to_ledger(self, period_key: str, manual: list[ProductLine]) -> None:
        source = _SHEET_SOURCE_PREFIX + period_key
        start, _ = _period_bounds(period_key)
        opening_date = start - timedelta(days=1)   # so it counts as đầu kỳ in NXT
        now = datetime.now()
        movements: list[InventoryMovement] = []
        for line in manual:
            item = self._items.find_by_code(line.code)
            name = line.name or (item.name if item else "")
            account = (item.account_code if item else "") or _PRODUCT_ACCOUNT
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
                    note="Bảng kê TP (155)", created_at=now,
                ))
        self._inventory.replace_source_movements(source, movements)
