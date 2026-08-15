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
from domain.models.product_sheet import ProductLine, ProductSheet, _unit
from domain.services.costing_service import CostingService
from domain.services.inventory_service import InventoryService
from domain.services.material_sheet_service import _period_bounds, _unit_cost
from domain.services.period_tag import child_period_keys

_SHEET_SOURCE_PREFIX = "BK-TP:"      # source tag for worksheet-pushed movements
_COSTING_SOURCE_PREFIX = "GT-TP:"    # nhập kho TP do chính bảng giá thành đẩy ra
_PRODUCT_ACCOUNT = "155"             # nhóm Thành phẩm (TT200)
_ZERO = Decimal("0")


class ProductSheetError(ValueError):
    pass


def previous_period_key(period_key: str) -> str:
    """'2026' → '2025'; '2026-06' → '2026-05'; '2026-01' → '2025-12';
    '2026-Q2' → '2026-Q1'; '2026-Q1' → '2025-Q4'."""
    parts = period_key.split("-")
    year = int(parts[0])
    if len(parts) == 1:
        return str(year - 1)
    if parts[1].upper().startswith("Q"):
        quarter = int(parts[1][1:])
        if quarter == 1:
            return f"{year - 1}-Q4"
        return f"{year}-Q{quarter - 1}"
    month = int(parts[1])
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


def _accumulate_product(
    merged: dict[str, ProductLine], code: str, line: ProductLine
) -> None:
    """Cộng một dòng của kỳ con vào dòng gộp của kỳ rộng."""
    target = merged.get(code)
    if target is None:
        # Kỳ con đầu tiên có mã này quyết định tồn đầu kỳ của cả kỳ rộng.
        merged[code] = ProductLine(
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
    target.in_price = _unit(target.in_value, target.in_qty)
    target.out_price = _unit(target.out_value, target.out_qty)


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
        own, inherited = self._split_saved_lines(period_key)
        if own or inherited:
            manual = [
                ln for ln in own + inherited
                if ln.code.strip() not in ledger_codes
            ]
        else:
            # First open of this period: tồn đầu kỳ = tồn cuối kỳ trước.
            manual = [
                ln for ln in self.carry_forward_lines(period_key)
                if ln.code.strip() not in ledger_codes
            ]
        for line in manual:
            line.recompute()
        return ProductSheet(period_key=period_key, lines=ledger_lines + manual)

    # ----- gộp bảng kê kỳ con (quý = ba tháng, năm = bốn quý) --------------

    def saved_lines(self, period_key: str) -> list[ProductLine]:
        """Dòng nhập tay có hiệu lực của kỳ, đã gộp từ các kỳ con."""
        own, inherited = self._split_saved_lines(period_key)
        return own + inherited

    def _split_saved_lines(
        self, period_key: str
    ) -> tuple[list[ProductLine], list[ProductLine]]:
        """Tách dòng khai ở đúng kỳ này khỏi dòng gộp lên từ kỳ con.

        Đầu kỳ lấy của kỳ con SỚM NHẤT có mã đó (đầu kỳ tháng 05 vốn đã là cuối
        kỳ tháng 04, cộng dồn là nhân đôi); nhập / xuất thì cộng dồn. Mã nào kỳ
        này đã tự khai thì số của kỳ này thắng.

        Dòng gộp mang cờ ``from_ledger``: kỳ rộng chỉ hiển thị, không sở hữu —
        nên save() không ghi/đẩy lại (kỳ con đã đẩy rồi) và ``recompute()`` để
        yên TT xuất đã cộng từ từng tháng thay vì tính bình quân lại cả quý.
        """
        own = self._repo.list_for_period(period_key)
        own_codes = {ln.code.strip() for ln in own if ln.code.strip()}
        merged: dict[str, ProductLine] = {}
        for child in child_period_keys(period_key):
            for line in self.saved_lines(child):
                code = line.code.strip()
                if not code or code in own_codes:
                    continue
                _accumulate_product(merged, code, line)
        return own, list(merged.values())

    def carry_forward_lines(self, period_key: str) -> list[ProductLine]:
        """Openings for *period_key* built from the previous period's closings."""
        carried: list[ProductLine] = []
        for prev in self.saved_lines(previous_period_key(period_key)):
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

    # ----- feed the costing sheet: SL nhập 155 → số lượng sản xuất ----------

    def input_quantities(self, period_key: str) -> list[tuple[str, str, Decimal]]:
        """``(mã, tên, SL nhập)`` thành phẩm trong kỳ theo cột Nhập·SL của bảng kê.

        Bảng tính giá thành dùng hàm này để tự lấy số lượng sản xuất: "bảng kê
        nhập bao nhiêu thì bảng giá thành hiện bấy nhiêu" — SL nhập kho 155 chính
        là số lượng thành phẩm cần tính giá thành, rồi từ định mức ra tiền 15401.

        Đọc đúng những gì cột Nhập·SL của bảng kê đang hiển thị: thành phẩm nhập
        kho bằng chứng từ thật (dòng sổ kho) **và** dòng nhập tay đã lưu. Cố tình
        **không** đọc phần nhập 155 do chính bảng giá thành đẩy ra (nguồn
        ``GT-TP``) để tránh vòng lặp giá thành ↔ số lượng. Gộp theo mã, giữ tên
        gặp đầu tiên, giữ thứ tự xuất hiện.
        """
        aggregated: dict[str, list] = {}

        def add(code: str, name: str, qty: Decimal) -> None:
            code = code.strip()
            if not code or qty <= _ZERO:
                return
            if code in aggregated:
                aggregated[code][1] += qty
            else:
                aggregated[code] = [name, qty]

        for r in self._production_rows(period_key):
            add(r.item_code, r.item_name, r.in_qty)
        for line in self.saved_lines(period_key):
            add(line.code, line.name, line.in_qty)
        return [(code, name, qty) for code, (name, qty) in aggregated.items()]

    def _production_rows(self, period_key: str) -> list[NxtRow]:
        """Dòng sổ kho 155 có nhập trong kỳ, trừ phần hai bảng tự đẩy ra.

        Bỏ ``BK-TP:`` (bản sao sổ kho của chính dòng nhập tay — đọc thẳng từ
        ``product_sheet_line`` rồi nên tính lần nữa là nhân đôi) và ``GT-TP:``
        (nhập kho do bảng giá thành sinh ra — đọc lại sẽ thành vòng lặp).
        """
        start, end = _period_bounds(period_key)
        rows = self._inventory.compute_nxt(
            start, end,
            exclude_source_prefix=(_SHEET_SOURCE_PREFIX, _COSTING_SOURCE_PREFIX),
        )
        return [
            r for r in rows
            if r.account_code == _PRODUCT_ACCOUNT and r.in_qty > _ZERO
        ]

    # ----- giá thành → Nhập·ĐG của bảng kê ----------------------------------

    def apply_costing_prices(self, sheet: ProductSheet) -> int:
        """Đưa giá thành đơn vị vừa tính về cột Nhập·ĐG của bảng kê.

        Chiều ngược của :meth:`input_quantities`, và cố ý tách bạch theo cột để
        hai bảng không giẫm chân nhau: **SL** luôn do bảng kê làm chủ (chảy sang
        giá thành), **ĐG/TT nhập** do bảng giá thành làm chủ (chảy về đây). Vì
        mỗi cột chỉ có một chiều nên chạy lại bao nhiêu lần cũng không lặp.

        ``Nhập·ĐG`` là cột dẫn xuất (= TT ÷ SL) nên ta gán TT = SL × giá thành
        đơn vị rồi để :meth:`ProductLine.recompute` suy ra đơn giá. Chỉ đụng dòng
        nhập tay: dòng sổ kho đã mang sẵn đơn giá của chứng từ.

        Trả về số dòng đã cập nhật.
        """
        costing = self._costing.load(sheet.period_key)
        unit_costs = {
            row.code.strip(): row.unit_cost
            for row in costing.rows
            if row.code.strip() and row.unit_cost > _ZERO
        }
        applied = 0
        for line in sheet.lines:
            if line.from_ledger or line.in_qty <= _ZERO:
                continue
            unit_cost = unit_costs.get(line.code.strip())
            if unit_cost is None:
                continue
            value = line.in_qty * unit_cost
            if line.in_value == value:
                continue
            line.in_value = value
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
