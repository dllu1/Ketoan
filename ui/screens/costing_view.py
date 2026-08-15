"""CostingView — editable "Bảng tính giá thành sản phẩm".

The user types each product's quantity and direct-material (NVL/15401) amount,
plus two shared cost pools: nhân công (15402) and SX chung (15403). The labor
and overhead columns are allocated live by NVL ratio (per the form's blue
notes); Tổng giá thành and Đơn giá (154/SP) follow.

Ô "15403" là **tổng** của 154032 (SX chung) + 154033 (chi phí khác): công ty chỉ
theo dõi một cấp ở bảng giá thành. Hai tài khoản vẫn tách ở danh mục tài khoản
và ở sổ cái để hạch toán riêng, và bút toán kết chuyển ``GT-155`` vẫn ghi Có
từng tài khoản — xem :meth:`CostingView._pools`.
"""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.period import active_period
from data.repositories.costing_repo import CostingRepository
from data.repositories.fixed_asset_repo import FixedAssetRepository
from data.repositories.product_sheet_repo import ProductSheetRepository
from domain.models.costing import CostingInput, CostPools
from domain.money import format_money, parse_money
from domain.services.bom_service import BomService
from domain.services.costing_pool_service import CostingPoolService
from domain.services.costing_service import CostingService
from domain.services.fixed_asset_service import FixedAssetService
from domain.services.material_issue_service import MaterialIssueService
from domain.services.product_sheet_service import ProductSheetService
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.enter_nav import install_grid_enter_nav
from ui.screens.material_sheet_view import period_key, _fmt_qty

# Bố cục cột theo tờ "Bảng tính giá thành sản phẩm": khối đơn giá/SP trước
# (15401/sp · 15402/sp · 15403/sp · 154/Sp), rồi khối tổng
# (15401 · 15402 · 15403 · Tổng giá thành · 154/Sp = tổng÷SL).
#
# Công ty gộp SX chung (154032) + chi phí khác (154033) thành **một** cấp 15403 ở
# cả ô nhập lẫn cột tổng — trước đây chỉ cột đơn giá "15403/sp" mới gộp. Hai tài
# khoản vẫn tách ở sổ cái và ở bút toán kết chuyển; chỉ bảng này hiển thị gộp.
_HEADERS = [
    "STT", "Mã", "Mặt hàng", "Số lượng",
    "15401/sp", "15402/sp", "15403/sp", "154/Sp",
    "15401", "15402", "15403",
    "Tổng giá thành", "154/Sp ",
]
(_STT, _CODE, _NAME, _QTY,
 _U_NVL, _U_LABOR, _U_OH_OTHER, _U_SUM,
 _NVL, _LABOR, _OH, _TOTAL, _UNIT) = range(13)

_EDITABLE = (_CODE, _NAME, _QTY, _NVL)
_COMPUTED = (_U_NVL, _U_LABOR, _U_OH_OTHER, _U_SUM,
             _LABOR, _OH, _TOTAL, _UNIT)


class CostingView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("CostingView")
        self._service = CostingService(CostingRepository())
        self._bom = BomService()
        self._issue = MaterialIssueService(bom=self._bom)
        # Bảng kê TP (155) cấp số lượng sản xuất: SL nhập kho 155 → cột Số lượng.
        self._product_sheet = ProductSheetService(ProductSheetRepository())
        # Sổ cái cấp pool chi phí: Nợ 15402 → ô nhân công; Nợ 154032+154033 → ô
        # SX chung (15403) gộp.
        self._pool_service = CostingPoolService()
        # material_code -> đơn giá xuất bình quân gia quyền của kỳ; refreshed on
        # reload and used to auto-derive the NVL column for sản phẩm có định mức.
        self._cost_of = lambda _code: Decimal("0")
        self._updating = False
        # Pool nào người dùng đã tự gõ → giữ nguyên, không cho sổ cái ghi đè.
        self._manual: dict[str, bool] = {
            "labor": False, "overhead": False, "other": False
        }
        # Ô "15403" gộp 154032 + 154033. Phần 154033 (chi phí khác) được nhớ
        # riêng ở đây để bút toán kết chuyển vẫn ghi Có đúng từng tài khoản —
        # người dùng gõ vào ô gộp thì chênh lệch dồn vào 154032.
        self._other_share = Decimal("0")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        self._caption = QLabel()
        self._caption.setObjectName("SectionLabel")
        root.addWidget(self._caption)

        # ----- cost pools (shared across products) -----------------------
        pools = QHBoxLayout()
        pools.setSpacing(10)
        self._labor = self._pool_field("Nhân công (15402)", "labor", pools)
        self._overhead = self._pool_field("SX chung (15403)", "overhead", pools)
        pools.addStretch(1)
        root.addLayout(pools)

        # ----- toolbar ---------------------------------------------------
        toolbar = QHBoxLayout()
        btn_add = Button("+ Thêm dòng", icon_name="plus")
        btn_add.clicked.connect(lambda: self._add_row())
        btn_del = Button("− Xóa dòng", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_del.clicked.connect(self._remove_current_row)
        btn_bom = Button("Lấy NVL theo định mức", icon_name="download")
        btn_bom.clicked.connect(self._fill_material_from_bom)
        btn_depr = Button("Lấy KH máy SX (15403)", icon_name="download")
        btn_depr.clicked.connect(self._fill_overhead_from_depreciation)
        btn_save = Button("Lưu", variant=ButtonVariant.PRIMARY, icon_name="check")
        btn_save.clicked.connect(self._on_save)
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_del)
        toolbar.addWidget(btn_bom)
        toolbar.addWidget(btn_depr)
        toolbar.addStretch(1)
        toolbar.addWidget(btn_save)
        root.addLayout(toolbar)

        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(_NAME, QHeaderView.Stretch)
        self._table.itemChanged.connect(self._on_item_changed)
        # Enter = sang ô sửa được kế tiếp; hết bảng thì tự mở dòng mới.
        install_grid_enter_nav(self._table, add_row=self._add_row)
        root.addWidget(self._table, 1)

        self._summary = QLabel()
        self._summary.setObjectName("BalanceBar")
        self._summary.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(self._summary)

        self.reload()

    def _pool_field(self, label: str, key: str, layout: QHBoxLayout) -> QLineEdit:
        layout.addWidget(QLabel(label))
        edit = QLineEdit()
        edit.setPlaceholderText("0")
        edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        edit.setMaximumWidth(150)
        edit.textChanged.connect(lambda _, k=key: self._on_pool_edited(k))
        layout.addWidget(edit)
        return edit

    def _on_pool_edited(self, key: str) -> None:
        """Người dùng gõ vào một ô pool → khóa ô đó lại, sổ cái không ghi đè nữa.

        ``reload()`` cũng gọi ``setText`` nên cũng phát ``textChanged``; cờ
        ``_updating`` phân biệt "máy đổ số" với "người gõ".

        Ô "15403" gộp hai tài khoản nên khóa cả hai: đã gõ tay thì cả 154032 lẫn
        154033 đều thôi lấy theo sổ cái, nếu không tổng hiển thị sẽ lại trôi.
        """
        if self._updating:
            return
        self._manual[key] = True
        if key == "overhead":
            self._manual["other"] = True
        self._recompute()

    # ----- public --------------------------------------------------------

    def reload(self) -> None:
        self._updating = True
        self._table.setRowCount(0)
        self._cost_of = self._issue.cost_fn(period_key())
        pools, inputs = CostingRepository().load(period_key())
        inputs = self._merge_product_quantities(period_key(), inputs)
        # Khôi phục "ô nào đã sửa tay" TRƯỚC khi trộn — _merge_pools dựa vào nó.
        self._manual = dict(pools.manual_flags)
        pools = self._merge_pools(pools)
        # Ô 15403 hiển thị tổng; phần 154033 nhớ riêng để tách lại lúc ghi sổ.
        self._other_share = pools.other
        combined = pools.overhead + pools.other
        self._labor.setText(format_money(pools.labor) if pools.labor else "")
        self._overhead.setText(format_money(combined) if combined else "")
        for inp in inputs:
            self._add_row(inp)
        if not inputs:
            self._add_row()
        self._updating = False
        self._caption.setText(
            f"Kỳ: {active_period().label}  ·  Số lượng lấy từ Bảng kê TP (155) – "
            "Nhập·SL  ·  Nhân công (15402) và SX chung 15403 = 154032 + 154033 lấy "
            "từ sổ cái rồi phân bổ theo tỷ lệ NVL  ·  NVL của SP có định mức tính "
            "tự động (ĐG xuất bình quân), trừ vào Xuất 152 khi lưu"
        )
        self._recompute()

    def _merge_pools(self, saved: CostPools) -> CostPools:
        """Quyết định số của từng pool: số người dùng sửa luôn thắng.

        Trả về vẫn tách 154032 / 154033; phần hiển thị gộp lại thành ô "15403" ở
        :meth:`reload`.

        Thứ tự ưu tiên cho từng pool:

        1. **Người dùng đã sửa tay** (cờ ``*_manual``) → giữ nguyên số đã lưu.
           Đây là điều kiện để ô đứng yên: chỉ đổi khi chính người dùng đổi.
        2. Chưa sửa tay và sổ cái có phát sinh → lấy từ sổ cái, để bút toán lương
           ``Nợ 15402 / Có 334`` không phải nhập lại lần hai.
        3. Còn lại → giữ số đã lưu.

        Sổ cái ở đây đã loại bút toán kết chuyển ``GT-155/…`` do chính bảng này
        sinh ra (xem :mod:`domain.services.costing_pool_service`), nếu không pool
        sẽ tự trừ đúng bằng số vừa phân bổ sau mỗi lần lưu.
        """
        period = active_period()
        ledger = self._pool_service.pools_for(period.date_from, period.date_to)
        zero = Decimal("0")

        def pick(name: str, from_ledger: Decimal, from_saved: Decimal) -> Decimal:
            if self._manual[name]:
                return from_saved
            return from_ledger if from_ledger != zero else from_saved

        return CostPools(
            labor=pick("labor", ledger.labor, saved.labor),
            overhead=pick("overhead", ledger.overhead, saved.overhead),
            other=pick("other", ledger.other, saved.other),
            labor_manual=self._manual["labor"],
            overhead_manual=self._manual["overhead"],
            other_manual=self._manual["other"],
        )

    def _merge_product_quantities(
        self, key: str, inputs: list[CostingInput]
    ) -> list[CostingInput]:
        """Đổ SL sản xuất từ Bảng kê TP (155) vào danh sách SP của bảng giá thành.

        "Bảng kê nhập bao nhiêu thì bảng giá thành hiện bấy nhiêu": mỗi thành phẩm
        có SL nhập kho 155 trong kỳ lấy đúng số lượng đó (ghi đè SL đã lưu). SP
        chưa có trong bảng giá thành được thêm để từ định mức tính ra 15401. SP đã
        lưu mà kỳ này không nhập 155 vẫn giữ nguyên (không xóa NVL nhập tay).
        """
        by_code = {inp.code.strip(): inp for inp in inputs if inp.code.strip()}
        merged = list(inputs)
        for code, name, qty in self._product_sheet.input_quantities(key):
            existing = by_code.get(code)
            if existing is not None:
                existing.quantity = qty
                if not existing.name:
                    existing.name = name
            else:
                new = CostingInput(code=code, name=name, quantity=qty)
                by_code[code] = new
                merged.append(new)
        return merged

    # ----- rows ----------------------------------------------------------

    def _add_row(self, inp: CostingInput | None = None) -> None:
        was_updating = self._updating
        self._updating = True
        row = self._table.rowCount()
        self._table.insertRow(row)
        values = [""] * len(_HEADERS)
        if inp is not None:
            values[_CODE] = inp.code
            values[_NAME] = inp.name
            values[_QTY] = _fmt_qty(inp.quantity)
            values[_NVL] = format_money(inp.material_cost)
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col not in (_CODE, _NAME):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if col not in _EDITABLE:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row, col, item)
        self._updating = was_updating
        if not was_updating:
            self._recompute()

    def _remove_current_row(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)
            self._recompute()

    def _fill_material_from_bom(self) -> None:
        """Fill the NVL (15401) column from each product's định mức × số lượng.

        Uses the period weighted-average issue price (đơn giá xuất) so the number
        matches what will be issued from 152 on save.
        """
        filled = 0
        self._updating = True
        for row in range(self._table.rowCount()):
            code = self._cell(row, _CODE)
            qty = self._num(row, _QTY)
            if not code or qty <= Decimal("0"):
                continue
            cost = self._bom.material_cost(code, qty, self._cost_of)
            if cost > Decimal("0"):
                self._set(row, _NVL, format_money(cost))
                filled += 1
        self._updating = False
        self._recompute()
        if filled == 0:
            QMessageBox.information(
                self, "Định mức",
                "Chưa có định mức cho các mặt hàng (hoặc thiếu số lượng / đơn giá NVL).\n"
                "Khai định mức trong Danh mục → Định mức.",
            )

    def _fill_overhead_from_depreciation(self) -> None:
        """Đưa khấu hao máy móc sản xuất (TK 15403/627) của kỳ vào pool SX chung.

        Máy móc dùng cho sản xuất khai "TK chi phí KH" = 15403 ở màn Tài sản cố
        định; khấu hao của chúng là chi phí sản xuất chung nên phải nằm trong ô
        SX chung (15403) rồi phân bổ vào giá thành theo tỷ lệ NVL.

        Ô đó thường đã có tiền điện / nước gõ tay, nên khi ô đang có số ta HỎI
        cộng thêm hay thay thế — trước đây nút này ghi đè, làm mất số cũ.

        Nếu bút toán khấu hao tháng (``KH-YYYYMM``, ``Nợ 15403 / Có 214``) đã
        được ghi sổ thì số đó vốn đã nằm trong ô (pool tự lấy từ sổ cái), nên
        bấm nút này nữa là tính hai lần — ta cảnh báo trước khi cộng.
        """
        period = active_period()
        amount = FixedAssetService(FixedAssetRepository()).production_depreciation(
            period.year, period.months
        )
        if amount <= Decimal("0"):
            QMessageBox.information(
                self, "Khấu hao sản xuất",
                f"Kỳ {period.label} không có khấu hao máy móc sản xuất.\n"
                "Vào Tài sản cố định → Sửa và đặt \"TK chi phí KH\" = 15403 cho "
                "máy móc dùng để sản xuất.",
            )
            return
        posted = self._pool_service.posted_production_depreciation(
            period.year, period.months
        )
        if posted > Decimal("0") and not self._confirm_double_depreciation(posted):
            return
        current = self._pool_amount(self._overhead)
        total = amount
        if current > Decimal("0"):
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("Khấu hao sản xuất")
            box.setText(f"Ô SX chung (15403) đang có {format_money(current)}.")
            box.setInformativeText(
                f"Khấu hao máy sản xuất {period.label} là {format_money(amount)}.\n"
                "Cộng thêm vào số đang có, hay thay thế bằng khấu hao?"
            )
            add_btn = box.addButton("Cộng thêm", QMessageBox.AcceptRole)
            replace_btn = box.addButton("Thay thế", QMessageBox.DestructiveRole)
            box.addButton("Hủy", QMessageBox.RejectRole)
            box.setDefaultButton(add_btn)
            box.exec()
            clicked = box.clickedButton()
            if clicked is add_btn:
                total = current + amount
            elif clicked is replace_btn:
                total = amount
            else:
                return
        # setText phát textChanged → _on_pool_edited đánh dấu ô là "sửa tay" và
        # chạy _recompute; từ đây sổ cái không ghi đè ô SX chung nữa.
        self._overhead.setText(format_money(total))
        QMessageBox.information(
            self, "Khấu hao sản xuất",
            f"Đã đưa {format_money(amount)} khấu hao máy móc sản xuất "
            f"({period.label}) vào ô SX chung (15403) — hiện là {format_money(total)}.",
        )

    def _confirm_double_depreciation(self, posted: Decimal) -> bool:
        """Hỏi lại khi khấu hao máy SX đã được ghi sổ và đã có trong pool."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Khấu hao đã ghi sổ")
        box.setText(
            f"Khấu hao máy sản xuất kỳ này ĐÃ được ghi sổ "
            f"({format_money(posted)} Nợ 15403)."
        )
        box.setInformativeText(
            "Ô SX chung đã tự lấy số đó từ sổ cái, nên cộng thêm lần nữa sẽ tính "
            "khấu hao hai lần vào giá thành.\n\nVẫn muốn cộng?"
        )
        box.addButton("Hủy", QMessageBox.RejectRole)
        proceed = box.addButton("Vẫn cộng", QMessageBox.DestructiveRole)
        box.setDefaultButton(box.buttons()[0])
        box.exec()
        return box.clickedButton() is proceed

    # ----- compute -------------------------------------------------------

    def _on_item_changed(self, _item: QTableWidgetItem) -> None:
        if self._updating:
            return
        self._recompute()

    def _recompute(self) -> None:
        if self._updating:
            return
        self._updating = True
        # NVL của sản phẩm có định mức luôn = Σ định mức × SL × ĐG xuất bình quân,
        # nên cột NVL khớp đúng phần sẽ trừ vào Xuất 152. SP không có định mức giữ
        # nguyên giá trị nhập tay.
        for row in range(self._table.rowCount()):
            code = self._cell(row, _CODE)
            if code and self._bom.has_bom(code):
                cost = self._bom.material_cost(
                    code, self._num(row, _QTY), self._cost_of
                )
                self._set(row, _NVL, format_money(cost))
        inputs = [self._input_at(r) for r in range(self._table.rowCount())]
        sheet = self._service.compute(inputs, self._pools())
        for row, cost in enumerate(sheet.rows):
            self._set(row, _STT, str(row + 1))
            # Khối đơn giá / SP (15401/sp · 15402/sp · 15403/sp · 154/Sp).
            self._set(row, _U_NVL, format_money(cost.unit_material))
            self._set(row, _U_LABOR, format_money(cost.unit_labor))
            self._set(row, _U_OH_OTHER, format_money(cost.unit_overhead_other))
            self._set(row, _U_SUM, format_money(cost.unit_components_sum))
            # Khối tổng (15402 · 15403 · Tổng giá thành · 154/Sp). Cột 15403 gộp
            # SX chung + chi phí khác, khớp với cột đơn giá "15403/sp".
            self._set(row, _LABOR, format_money(cost.labor_cost))
            self._set(row, _OH,
                      format_money(cost.overhead_cost + cost.other_cost))
            self._set(row, _TOTAL, format_money(cost.total_cost))
            self._set(row, _UNIT, format_money(cost.unit_cost))
        self._updating = False
        summary = (
            "Tổng giá thành: " + format_money(sheet.grand_total)
            + "   ·   NVL: " + format_money(sheet.total_material)
            + "   ·   Tương ứng: " + format_money(sheet.total_allocated)
        )
        unallocated = sheet.unallocated_pools
        if unallocated > Decimal("0"):
            summary += (
                "   ·   ✗ CHƯA PHÂN BỔ ĐƯỢC " + format_money(unallocated)
                + " (Σ NVL = 0)"
            )
        self._summary.setText(summary)
        self._summary.setProperty(
            "balanced", "false" if unallocated > Decimal("0") else "true"
        )
        self._summary.style().unpolish(self._summary)
        self._summary.style().polish(self._summary)

    def _set(self, row: int, col: int, text: str) -> None:
        item = self._table.item(row, col)
        if item is not None:
            item.setText(text)

    # ----- model in/out --------------------------------------------------

    def _cell(self, row: int, col: int) -> str:
        item = self._table.item(row, col)
        return item.text().strip() if item else ""

    def _num(self, row: int, col: int) -> Decimal:
        try:
            return parse_money(self._cell(row, col))
        except ValueError:
            return Decimal("0")

    def _input_at(self, row: int) -> CostingInput:
        return CostingInput(
            code=self._cell(row, _CODE),
            name=self._cell(row, _NAME),
            quantity=self._num(row, _QTY),
            material_cost=self._num(row, _NVL),
        )

    def _pool_amount(self, field: QLineEdit) -> Decimal:
        try:
            return parse_money(field.text())
        except ValueError:
            return Decimal("0")

    def _pools(self) -> CostPools:
        """Tách số ở ô gộp "15403" về lại 154032 và 154033.

        Bảng chỉ hiển thị một ô, nhưng bút toán kết chuyển phải ghi Có đúng từng
        tài khoản thì 154032/154033 mới tất toán được về 0. Phần 154033 giữ theo
        số đã có (``_other_share``, lấy từ sổ cái hoặc lần lưu trước); chênh lệch
        do người dùng gõ dồn vào 154032 — 154033 chỉ phát sinh khi có bút toán
        thật, nên đó là chỗ hợp lý để nhận phần gõ tay.
        """
        combined = self._pool_amount(self._overhead)
        other = min(self._other_share, combined) if combined > Decimal("0") else combined
        return CostPools(
            labor=self._pool_amount(self._labor),
            overhead=combined - other,
            other=other,
            labor_manual=self._manual["labor"],
            overhead_manual=self._manual["overhead"],
            other_manual=self._manual["other"],
        )

    def _on_save(self) -> None:
        inputs = [self._input_at(r) for r in range(self._table.rowCount())]
        preview = self._service.compute(inputs, self._pools())
        if preview.unallocated_pools > Decimal("0"):
            confirm = QMessageBox.question(
                self, "Chi phí chưa phân bổ",
                f"{format_money(preview.unallocated_pools)} nhân công / SX chung / "
                "chi phí khác KHÔNG vào được giá thành vì tổng NVL của kỳ bằng 0.\n\n"
                "Phân bổ dựa trên tỷ lệ NVL — hãy khai định mức "
                "(Danh mục → Định mức) hoặc nhập cột 15401 trước.\n\nVẫn lưu?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return
        sheet = self._service.save(period_key(), inputs, self._pools())
        # Trừ NVL theo định mức vào Xuất 152 (theo mã từng loại NVL). Chỉ SP có
        # định mức phát sinh xuất; SP nhập tay NVL không tách được theo mã.
        products = [
            (inp.code.strip(), inp.quantity)
            for inp in inputs
            if inp.code.strip() and inp.quantity > Decimal("0")
        ]
        consumed = self._issue.post(period_key(), products)
        # Đẩy giá thành đơn vị ngược về nhập kho 155 — CHỈ đơn giá. Số lượng vẫn
        # là của chứng từ nhập kho; bảng này không tạo thêm lượng nhập nào (tạo
        # mới chính là thứ từng làm số lượng bị cộng đôi).
        self._issue.reprice_finished_goods(
            period_key(),
            [(r.code.strip(), r.quantity, r.unit_cost)
             for r in sheet.rows if r.code.strip()],
        )
        self._post_costing_entries(sheet)
        QMessageBox.information(
            self, "Đã lưu",
            f"Đã lưu bảng tính giá thành cho kỳ {active_period().label}.\n"
            + self._consumption_summary(consumed)
            + ("\n" + f"Đã kết chuyển giá thành {format_money(sheet.grand_total)} "
               "sang 155 (Nợ 155 / Có 15401·15402·154032·154033).\n"
               "Số lượng thành phẩm giữ nguyên theo Bảng kê TP (155)."
               if sheet.grand_total > Decimal("0") else ""),
        )

    def _post_costing_entries(self, sheet) -> None:
        """Ghi sổ hai bút toán khép kín vòng 152 → 154 → 155.

        Trước đây chỉ có ``Nợ 155 / Có 154``: TK 154 chỉ có phát sinh Có, còn
        NVL xuất dùng thì trừ kho mà không hề vào sổ cái, nên số dư 154 và 152
        đều sai. Nay ghi đủ hai vế:

        * ``GT-NVL/<kỳ>``  Nợ 15401 / Có 152  — NVL xuất dùng cho sản xuất, khớp
          đúng phần đã trừ ở cột Xuất của Bảng kê NVL chính.
        * ``GT-155/<kỳ>``  Nợ 155 / Có 15401·15402·154032·154033 — kết chuyển giá
          thành sang thành phẩm. Ghi Có **từng tài khoản con** đúng số đã tập hợp
          nên các TK 1540x tự tất toán về 0, thay vì treo lơ lửng ở TK cha 154.

        Cả hai idempotent theo số chứng từ: lưu lại bảng giá thành thì thay bút
        toán cũ chứ không cộng dồn.
        """
        from data.repositories.journal_repo import JournalRepository
        from domain.models.journal import EntryStatus, JournalEntry, JournalLine
        from domain.services.journal_service import JournalService

        journal = JournalService(JournalRepository())
        period = active_period()
        zero = Decimal("0")

        nvl_ref = f"GT-NVL/{period_key()}"
        journal.delete_by_ref(nvl_ref)
        if sheet.total_material > zero:
            journal.create(JournalEntry(
                ref=nvl_ref,
                entry_date=period.date_to,
                description=f"Xuất NVL cho sản xuất {period.label}",
                status=EntryStatus.POSTED,
                lines=[
                    JournalLine(account_code="15401",
                                account_name="Chi phí NVL trực tiếp",
                                description="Xuất NVL theo định mức",
                                debit=sheet.total_material),
                    JournalLine(account_code="152", account_name="Nguyên liệu, vật liệu",
                                description="Xuất kho NVL",
                                credit=sheet.total_material),
                ],
            ))

        ref = f"GT-155/{period_key()}"
        journal.delete_by_ref(ref)
        total = sheet.grand_total
        if total <= zero:
            return
        # Có từng TK chi phí đúng số đã tập hợp; tổng luôn bằng Nợ 155.
        credits = (
            ("15401", "Chi phí NVL trực tiếp", sheet.total_material),
            ("15402", "Chi phí nhân công trực tiếp", sheet.total_labor),
            ("154032", "Chi phí sản xuất chung", sheet.total_overhead),
            ("154033", "Chi phí khác", sheet.total_other),
        )
        journal.create(JournalEntry(
            ref=ref,
            entry_date=period.date_to,
            description=f"Kết chuyển giá thành sang thành phẩm {period.label}",
            status=EntryStatus.POSTED,
            lines=[
                JournalLine(account_code="155", account_name="Thành phẩm",
                            description="Nhập kho thành phẩm", debit=total),
            ] + [
                JournalLine(account_code=code, account_name=name,
                            description="Kết chuyển giá thành", credit=amount)
                for code, name, amount in credits if amount > zero
            ],
        ))

    @staticmethod
    def _consumption_summary(consumed: dict) -> str:
        if not consumed:
            return (
                "Chưa có định mức (BOM) nên không phát sinh xuất NVL. "
                "Khai định mức trong Danh mục → Định mức để tự trừ vào Xuất 152."
            )
        total = sum((value for _q, value in consumed.values()), Decimal("0"))
        return (
            f"Đã xuất {len(consumed)} loại NVL khỏi kho 152 theo định mức "
            f"(tổng {format_money(total)}); xem ở Nhập–Xuất–Tồn."
        )
