"""MaterialCostView — "Bảng tính nguyên vật liệu trực tiếp (TK 15401)" (chỉ xem).

Ma trận SP × loại NVL: chi tiết cột NVL (15401) của Bảng tính giá thành. Mỗi ô =
thành tiền loại NVL đó dùng cho SP đó (định mức × SL × đơn giá xuất bình quân của
kỳ). Cột "Cộng" mỗi dòng khớp đúng cột 15401 của SP bên tab Giá thành SP.

Chỉ đọc — dữ liệu suy ra hoàn toàn từ danh sách SP (bảng giá thành của kỳ), định
mức (BomService) và đơn giá xuất (MaterialIssueService). Các cột NVL sinh động
theo những mã NVL thực có trong định mức.
"""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.period import active_period
from data.repositories.costing_repo import CostingRepository
from domain.money import format_money
from domain.services.bom_service import BomService
from domain.services.material_issue_service import MaterialIssueService
from ui.screens.material_sheet_view import period_key, _fmt_qty
from ui.tokens import active_tokens

# Cột cố định bên trái; các cột NVL chèn giữa; cột "Cộng" ở cuối.
_FIXED_LEFT = ["STT", "Mã", "Mặt hàng", "Số lượng"]
(_C_STT, _C_CODE, _C_NAME, _C_QTY) = range(4)


class MaterialCostView(QWidget):
    """Bảng tính NVL trực tiếp (TK 15401) — read-only, dựng theo kỳ đang chọn."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("MaterialCostView")
        self._bom = BomService()
        self._issue = MaterialIssueService(bom=self._bom)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        self._caption = QLabel()
        self._caption.setObjectName("SectionLabel")
        self._caption.setWordWrap(True)
        root.addWidget(self._caption)

        self._table = QTableWidget(0, 0)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        root.addWidget(self._table, 1)

        self._summary = QLabel()
        self._summary.setObjectName("BalanceBar")
        self._summary.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(self._summary)

        self.reload()

    # ----- data ----------------------------------------------------------

    def reload(self) -> None:
        key = period_key()
        _pools, inputs = CostingRepository().load(key)
        products = [(i.code, i.name, i.quantity) for i in inputs if i.code.strip()]
        cost_fn = self._issue.cost_fn(key)
        matrix = self._bom.material_matrix(products, cost_fn)

        materials = matrix.materials
        headers = _FIXED_LEFT + [self._mat_header(matrix, m) for m in materials] + ["Cộng"]
        self._table.clear()
        self._table.setColumnCount(len(headers))
        self._table.setRowCount(0)
        self._table.setHorizontalHeaderLabels(headers)
        col_cong = len(headers) - 1
        for c, m in enumerate(materials):
            self._table.horizontalHeaderItem(_C_QTY + 1 + c).setToolTip(
                f"{m} — {matrix.material_names.get(m, m)}"
            )

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(_C_NAME, QHeaderView.Stretch)

        for idx, mrow in enumerate(matrix.rows):
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._set(row, _C_STT, str(idx + 1))
            self._set(row, _C_CODE, mrow.product_code)
            self._set(row, _C_NAME, mrow.product_name)
            self._set(row, _C_QTY, _fmt_qty(mrow.quantity), num=True)
            for c, m in enumerate(materials):
                value = mrow.value_of(m)
                self._set(row, _C_QTY + 1 + c,
                          format_money(value) if value else "–", num=True)
            self._set(row, col_cong, format_money(mrow.total_value), num=True, bold=True)

        # ----- ba dòng chân bảng: SL xuất / Đơn giá / Cộng tiền ------------
        self._add_footer(matrix, "Cộng SL xuất",
                         lambda m: _fmt_qty(matrix.material_qty(m)), total="")
        self._add_footer(matrix, "Đơn giá xuất",
                         lambda m: format_money(matrix.unit_prices.get(m, Decimal("0"))),
                         total="")
        self._add_footer(matrix, "Cộng tiền (15401)",
                         lambda m: format_money(matrix.material_value(m)),
                         total=format_money(matrix.grand_total))

        self._caption.setText(
            f"Kỳ: {active_period().label}  ·  Chi tiết cột NVL (15401) theo từng "
            "loại nguyên vật liệu (định mức × SL × đơn giá xuất bình quân)  ·  "
            "Cột “Cộng” mỗi dòng = cột 15401 của sản phẩm bên Giá thành SP"
        )
        if not materials:
            self._summary.setText(
                "Chưa có định mức (BOM) cho các sản phẩm trong kỳ — "
                "khai định mức trong Danh mục → Định mức để dựng bảng này."
            )
        else:
            self._summary.setText(
                "Tổng NVL trực tiếp (15401): " + format_money(matrix.grand_total)
            )

    # ----- helpers -------------------------------------------------------

    @staticmethod
    def _mat_header(matrix, material_code: str) -> str:
        name = matrix.material_names.get(material_code, "")
        return name or material_code

    def _set(self, row: int, col: int, text: str, *, num: bool = False,
             bold: bool = False) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        if num:
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if bold:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        self._table.setItem(row, col, item)

    def _add_footer(self, matrix, label: str, value_of, *, total: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._set(row, _C_NAME, label, bold=True)
        for c, m in enumerate(matrix.materials):
            self._set(row, _C_QTY + 1 + c, value_of(m), num=True, bold=True)
        if total:
            self._set(row, self._table.columnCount() - 1, total, num=True, bold=True)
        brand = QColor(active_tokens().brand)
        for col in range(self._table.columnCount()):
            item = self._table.item(row, col)
            if item is not None:
                item.setForeground(brand)
