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
from domain.services.period_tag import child_period_keys

_SHEET_SOURCE_PREFIX = "BK-NVL:"     # source tag for worksheet-pushed movements
_COSTING_SOURCE_PREFIX = "GT-NVL:"   # xuất NVL theo giá thành (do bảng giá thành đẩy)
_MATERIAL_ACCOUNT = "152"            # nhóm Nguyên vật liệu (TT200)
_ZERO = Decimal("0")
_ONE = Decimal("1")


class MaterialSheetError(ValueError):
    pass


def _period_bounds(period_key: str) -> tuple[date, date]:
    """[start, end] dates for a period_key ('2026', '2026-06' hoặc '2026-Q2')."""
    parts = period_key.split("-")
    year = int(parts[0])
    if len(parts) == 1:
        return date(year, 1, 1), date(year, 12, 31)
    if parts[1].upper().startswith("Q"):
        first = (int(parts[1][1:]) - 1) * 3 + 1
        return _month_bounds(year, first)[0], _month_bounds(year, first + 2)[1]
    return _month_bounds(year, int(parts[1]))


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = (date(year, 12, 31) if month == 12
           else date(year, month + 1, 1) - timedelta(days=1))
    return start, end


def _unit_cost(value: Decimal, qty: Decimal) -> Decimal:
    return (value / qty).quantize(_ONE) if qty else _ZERO


def _accumulate_material(
    merged: dict[str, MaterialLine], code: str, line: MaterialLine
) -> None:
    """Cộng một dòng của kỳ con vào dòng gộp của kỳ rộng."""
    target = merged.get(code)
    if target is None:
        # Kỳ con đầu tiên có mã này quyết định tồn đầu kỳ của cả kỳ rộng.
        merged[code] = MaterialLine(
            code=code, name=line.name, unit=line.unit,
            opening_price=line.opening_price,
            opening_qty=line.opening_qty,
            opening_value=line.opening_value,
            in_price=line.in_price, in_qty=line.in_qty, in_value=line.in_value,
            out_price=line.out_price, out_qty=line.out_qty,
            out_value=line.out_value,
            from_ledger=True,
        )
        return
    target.name = target.name or line.name
    target.unit = target.unit or line.unit
    target.in_qty += line.in_qty
    target.in_value += line.in_value
    target.out_qty += line.out_qty
    target.out_value += line.out_value
    target.in_price = _unit_cost(target.in_value, target.in_qty)
    target.out_price = _unit_cost(target.out_value, target.out_qty)


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
        own, inherited = self._split_saved_lines(period_key)
        manual = [
            line for line in own + inherited
            if line.code.strip() not in ledger_codes
        ]
        lines = ledger_lines + manual
        self._attach_costing_issues(period_key, lines)
        return MaterialSheet(period_key=period_key, lines=lines)

    # ----- gộp bảng kê kỳ con (quý = ba tháng, năm = bốn quý) --------------

    def saved_lines(self, period_key: str) -> list[MaterialLine]:
        """Dòng nhập tay có hiệu lực của kỳ, đã gộp từ các kỳ con."""
        own, inherited = self._split_saved_lines(period_key)
        return own + inherited

    def _split_saved_lines(
        self, period_key: str
    ) -> tuple[list[MaterialLine], list[MaterialLine]]:
        """Tách dòng khai ở đúng kỳ này khỏi dòng gộp lên từ kỳ con.

        Đầu kỳ lấy của kỳ con SỚM NHẤT có mã đó (không cộng dồn — đầu kỳ tháng
        05 vốn đã là cuối kỳ tháng 04); nhập / xuất thì cộng dồn. Mã nào kỳ này
        đã tự khai thì số của kỳ này thắng, tránh cộng đôi.

        Dòng gộp mang cờ ``from_ledger``: kỳ rộng chỉ hiển thị, không sở hữu —
        sửa thì vào đúng bảng tháng, và save() không ghi/đẩy lại sổ kho (bảng
        kê của kỳ con đã đẩy rồi, đẩy nữa là trừ kho hai lần).
        """
        own = self._repo.list_for_period(period_key)
        own_codes = {ln.code.strip() for ln in own if ln.code.strip()}
        merged: dict[str, MaterialLine] = {}
        for child in child_period_keys(period_key):
            for line in self.saved_lines(child):
                code = line.code.strip()
                if not code or code in own_codes:
                    continue
                _accumulate_material(merged, code, line)
        return own, list(merged.values())

    def _attach_costing_issues(
        self, period_key: str, lines: list[MaterialLine]
    ) -> None:
        """Gắn phần NVL đã xuất theo giá thành (GT-NVL) vào cột Xuất của bảng kê.

        Phần này nằm trong sổ kho nhưng bị :meth:`_ledger_material_rows` loại ra,
        nên trước đây lưu bảng giá thành xong mở bảng kê NVL chính vẫn thấy
        Xuất = 0. Nó thuộc về sổ kho chứ không phải bảng kê, nên đưa vào
        ``issued_*``: hiển thị và trừ tồn, nhưng không lưu lại và không đẩy lại
        sổ kho (tránh trừ kho hai lần).

        Vật tư chỉ bị tiêu hao mà chưa có dòng nào trong bảng thì thêm một dòng
        chỉ-đọc, nếu không khoản xuất đó biến mất khỏi bảng.
        """
        issued = self._issued_by_costing(period_key)
        if not issued:
            return
        by_code = {line.code.strip(): line for line in lines if line.code.strip()}
        for code, (qty, value) in sorted(issued.items()):
            line = by_code.get(code)
            if line is None:
                item = self._items.find_by_code(code)
                line = MaterialLine(
                    code=code,
                    name=item.name if item else "",
                    unit=item.unit if item else "",
                    from_ledger=True,
                )
                lines.append(line)
            line.issued_qty = qty
            line.issued_value = value

    def _issued_by_costing(
        self, period_key: str
    ) -> dict[str, tuple[Decimal, Decimal]]:
        """{mã: (SL, TT)} NVL xuất theo giá thành trong kỳ (nguồn ``GT-NVL``).

        Lấy bằng hiệu của hai lượt NXT chỉ khác nhau ở chỗ có loại ``GT-NVL`` hay
        không, nên chỉ dùng API công khai của sổ kho.
        """
        start, end = _period_bounds(period_key)
        without = {
            r.item_code: r for r in self._inventory.compute_nxt(
                start, end,
                exclude_source_prefix=(_SHEET_SOURCE_PREFIX, _COSTING_SOURCE_PREFIX),
            )
        }
        with_issues = {
            r.item_code: r for r in self._inventory.compute_nxt(
                start, end, exclude_source_prefix=_SHEET_SOURCE_PREFIX,
            )
        }
        issued: dict[str, tuple[Decimal, Decimal]] = {}
        for code, row in with_issues.items():
            if row.account_code != _MATERIAL_ACCOUNT:
                continue
            base = without.get(code)
            qty = row.out_qty - (base.out_qty if base else _ZERO)
            value = row.out_value - (base.out_value if base else _ZERO)
            if qty > _ZERO or value > _ZERO:
                issued[code] = (qty, value)
        return issued

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
