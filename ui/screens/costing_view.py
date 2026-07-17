"""CostingView — editable "Bảng tính giá thành sản phẩm".

The user types each product's quantity and direct-material (NVL/15401) amount,
and the three shared cost pools (15402 / 154032 / 154033). The labor, overhead
and other columns are allocated live by NVL ratio (per the form's blue notes);
Tổng giá thành and Đơn giá (154/SP) follow.
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
from domain.models.costing import CostingInput, CostPools
from domain.money import format_money, parse_money
from domain.services.bom_service import BomService
from domain.services.costing_service import CostingService
from domain.services.material_issue_service import MaterialIssueService
from ui.primitives.button import Button, ButtonVariant
from ui.screens.material_sheet_view import period_key, _fmt_qty

_HEADERS = [
    "STT", "Mã", "Mặt hàng", "Số lượng", "NVL (15401)",
    "NC (15402)", "SXC (154032)", "Khác (154033)",
    "Tổng giá thành", "Đơn giá (154/SP)",
]
(_STT, _CODE, _NAME, _QTY, _NVL,
 _LABOR, _OH, _OTHER, _TOTAL, _UNIT) = range(10)

_EDITABLE = (_CODE, _NAME, _QTY, _NVL)
_COMPUTED = (_LABOR, _OH, _OTHER, _TOTAL, _UNIT)


class CostingView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("CostingView")
        self._service = CostingService(CostingRepository())
        self._bom = BomService()
        self._issue = MaterialIssueService(bom=self._bom)
        # material_code -> đơn giá xuất bình quân gia quyền của kỳ; refreshed on
        # reload and used to auto-derive the NVL column for sản phẩm có định mức.
        self._cost_of = lambda _code: Decimal("0")
        self._updating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        self._caption = QLabel()
        self._caption.setObjectName("SectionLabel")
        root.addWidget(self._caption)

        # ----- cost pools (shared across products) -----------------------
        pools = QHBoxLayout()
        pools.setSpacing(10)
        self._labor = self._pool_field("Nhân công (15402)", pools)
        self._overhead = self._pool_field("SX chung (154032)", pools)
        self._other = self._pool_field("Chi phí khác (154033)", pools)
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
        btn_save = Button("Lưu", variant=ButtonVariant.PRIMARY, icon_name="check")
        btn_save.clicked.connect(self._on_save)
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_del)
        toolbar.addWidget(btn_bom)
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
        root.addWidget(self._table, 1)

        self._summary = QLabel()
        self._summary.setObjectName("BalanceBar")
        self._summary.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(self._summary)

        self.reload()

    def _pool_field(self, label: str, layout: QHBoxLayout) -> QLineEdit:
        layout.addWidget(QLabel(label))
        edit = QLineEdit()
        edit.setPlaceholderText("0")
        edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        edit.setMaximumWidth(150)
        edit.textChanged.connect(lambda _: self._recompute())
        layout.addWidget(edit)
        return edit

    # ----- public --------------------------------------------------------

    def reload(self) -> None:
        self._updating = True
        self._table.setRowCount(0)
        self._cost_of = self._issue.cost_fn(period_key())
        pools, inputs = CostingRepository().load(period_key())
        self._labor.setText(format_money(pools.labor) if pools.labor else "")
        self._overhead.setText(format_money(pools.overhead) if pools.overhead else "")
        self._other.setText(format_money(pools.other) if pools.other else "")
        for inp in inputs:
            self._add_row(inp)
        if not inputs:
            self._add_row()
        self._updating = False
        self._caption.setText(
            f"Kỳ: {active_period().label}  ·  Tương ứng (NC/SXC/khác) phân bổ "
            "theo tỷ lệ NVL của từng sản phẩm  ·  NVL của SP có định mức được "
            "tính tự động (ĐG xuất bình quân) và trừ vào Xuất 152 khi lưu"
        )
        self._recompute()

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
            self._set(row, _LABOR, format_money(cost.labor_cost))
            self._set(row, _OH, format_money(cost.overhead_cost))
            self._set(row, _OTHER, format_money(cost.other_cost))
            self._set(row, _TOTAL, format_money(cost.total_cost))
            self._set(row, _UNIT, format_money(cost.unit_cost))
        self._updating = False
        self._summary.setText(
            "Tổng giá thành: " + format_money(sheet.grand_total)
            + "   ·   NVL: " + format_money(sheet.total_material)
            + "   ·   Tương ứng: "
            + format_money(sheet.total_labor + sheet.total_overhead + sheet.total_other)
        )

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
        return CostPools(
            labor=self._pool_amount(self._labor),
            overhead=self._pool_amount(self._overhead),
            other=self._pool_amount(self._other),
        )

    def _on_save(self) -> None:
        inputs = [self._input_at(r) for r in range(self._table.rowCount())]
        self._service.save(period_key(), inputs, self._pools())
        # Trừ NVL theo định mức vào Xuất 152 (theo mã từng loại NVL). Chỉ SP có
        # định mức phát sinh xuất; SP nhập tay NVL không tách được theo mã.
        products = [
            (inp.code.strip(), inp.quantity)
            for inp in inputs
            if inp.code.strip() and inp.quantity > Decimal("0")
        ]
        consumed = self._issue.post(period_key(), products)
        QMessageBox.information(
            self, "Đã lưu",
            f"Đã lưu bảng tính giá thành cho kỳ {active_period().label}.\n"
            + self._consumption_summary(consumed),
        )

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
