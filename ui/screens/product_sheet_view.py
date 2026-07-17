"""ProductSheetView — editable "Bảng kê Nhập–Xuất–Tồn thành phẩm (155)".

The accountant types đầu kỳ (SL·TT), nhập (SL·TT — or pulls them from the
period's costing sheet) and SL xuất. Every đơn giá, TT xuất and tồn cuối kỳ is
derived live per the form rules: ĐG xuất is the weighted average
(TT đầu + TT nhập) / (SL đầu + SL nhập); tồn đầu kỳ carries forward from the
previous period's closing. A negative closing balance blocks saving, exactly
like the NVL sheet.
"""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.period import active_period
from data.repositories.product_sheet_repo import ProductSheetRepository
from domain.models.product_sheet import ProductLine, ProductSheet
from domain.money import format_money, parse_money
from domain.services.product_sheet_service import (
    ProductSheetError,
    ProductSheetService,
)
from ui.primitives.button import Button, ButtonVariant
from ui.screens.material_sheet_view import _fmt_qty, period_key

_NEGATIVE = QColor("#ef4444")  # tồn cuối kỳ âm — không hợp lệ
_LEDGER = QColor("#64748b")    # dòng đồng bộ từ sổ kho (chỉ đọc)

_HEADERS = [
    "STT", "Mã TP", "Tên thành phẩm", "ĐVT",
    "ĐK·ĐG", "ĐK·SL", "ĐK·TT",
    "Nhập·ĐG", "Nhập·SL", "Nhập·TT",
    "Xuất·ĐG", "Xuất·SL", "Xuất·TT",
    "Tồn·ĐG", "Tồn·SL", "Tồn·TT",
]
(_STT, _CODE, _NAME, _UNIT,
 _O_PRICE, _O_QTY, _O_VAL,
 _I_PRICE, _I_QTY, _I_VAL,
 _X_PRICE, _X_QTY, _X_VAL,
 _C_PRICE, _C_QTY, _C_VAL) = range(16)

# The user types these; everything else is derived per the form rules.
_EDITABLE = (_CODE, _NAME, _UNIT, _O_QTY, _O_VAL, _I_QTY, _I_VAL, _X_QTY)


class ProductSheetView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ProductSheetView")
        self._service = ProductSheetService(ProductSheetRepository())
        self._updating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        self._caption = QLabel()
        self._caption.setObjectName("SectionLabel")
        self._caption.setWordWrap(True)
        root.addWidget(self._caption)

        toolbar = QHBoxLayout()
        btn_add = Button("+ Thêm dòng", icon_name="plus")
        btn_add.clicked.connect(lambda: self._add_row())
        btn_del = Button("− Xóa dòng", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_del.clicked.connect(self._remove_current_row)
        btn_costing = Button("Lấy nhập từ giá thành", icon_name="download")
        btn_costing.clicked.connect(self._pull_from_costing)
        self._btn_save = Button("Lưu", variant=ButtonVariant.PRIMARY, icon_name="check")
        self._btn_save.clicked.connect(self._on_save)
        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_del)
        toolbar.addWidget(btn_costing)
        toolbar.addStretch(1)
        toolbar.addWidget(self._btn_save)
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

    # ----- public --------------------------------------------------------

    def reload(self) -> None:
        """(Re)load the worksheet for the active period (carry-forward aware)."""
        self._updating = True
        self._table.setRowCount(0)
        sheet = self._service.load(period_key())
        for line in sheet.lines:
            self._add_row(line)
        if not sheet.lines:
            self._add_row()
        self._updating = False
        self._caption.setText(
            f"Kỳ: {active_period().label}  ·  Nhập·TT = giá thành trong kỳ  ·  "
            "Xuất·ĐG = (TT đầu + TT nhập) ÷ (SL đầu + SL nhập)  ·  "
            "Tồn đầu kỳ = tồn cuối kỳ trước  ·  Dòng xám = đồng bộ từ sổ kho"
        )
        self._recompute_all()

    # ----- row helpers ---------------------------------------------------

    def _add_row(self, line: ProductLine | None = None) -> None:
        was_updating = self._updating
        self._updating = True
        row = self._table.rowCount()
        self._table.insertRow(row)

        from_ledger = line.from_ledger if line is not None else False
        values = [""] * len(_HEADERS)
        if line is not None:
            values = [
                "",
                line.code, line.name, line.unit,
                _fmt_qty(line.opening_price), _fmt_qty(line.opening_qty),
                format_money(line.opening_value),
                _fmt_qty(line.in_price), _fmt_qty(line.in_qty),
                format_money(line.in_value),
                _fmt_qty(line.out_price), _fmt_qty(line.out_qty),
                format_money(line.out_value),
                "", "", "",
            ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col not in (_CODE, _NAME, _UNIT):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if col not in _EDITABLE or from_ledger:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if from_ledger and col != _STT:
                item.setForeground(_LEDGER)
            if col == _CODE:
                item.setData(Qt.UserRole, from_ledger)
            self._table.setItem(row, col, item)
        self._updating = was_updating
        if not was_updating:
            self._recompute_all()

    def _remove_current_row(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)
            self._recompute_all()

    def _pull_from_costing(self) -> None:
        """Fill SL·TT nhập from the period's costing sheet (Giá thành SP)."""
        sheet = self._sheet(include_ledger=True)
        applied = self._service.apply_costing(sheet)
        if applied == 0:
            QMessageBox.information(
                self, "Giá thành",
                "Chưa có bảng tính giá thành cho kỳ này (hoặc thiếu số lượng).\n"
                "Lập bảng ở tab Giá thành SP rồi quay lại đây.",
            )
            return
        self._updating = True
        self._table.setRowCount(0)
        for line in sheet.lines:
            self._add_row(line)
        self._updating = False
        self._recompute_all()

    # ----- compute -------------------------------------------------------

    def _on_item_changed(self, _item: QTableWidgetItem) -> None:
        if self._updating:
            return
        self._recompute_all()

    def _recompute_all(self) -> None:
        self._updating = True
        any_manual_negative = False
        for row in range(self._table.rowCount()):
            line = self._line_at(row)
            line.recompute()
            self._set(row, _STT, str(row + 1))
            if not line.from_ledger:
                self._set(row, _O_PRICE, _fmt_qty(line.opening_price))
                self._set(row, _I_PRICE, _fmt_qty(line.in_price))
                self._set(row, _X_PRICE, _fmt_qty(line.out_price))
                self._set(row, _X_VAL, format_money(line.out_value))
            self._set(row, _C_PRICE, _fmt_qty(line.closing_price))
            self._set_closing(row, _C_QTY, _fmt_qty(line.closing_qty),
                              line.closing_qty < 0)
            self._set_closing(row, _C_VAL, format_money(line.closing_value),
                              line.closing_value < 0)
            # Only rows this worksheet owns can block saving; a ledger-synced
            # row going negative is a real-stock issue, shown red but not blocking.
            if line.is_negative and not line.from_ledger:
                any_manual_negative = True
        self._updating = False

        sheet = self._sheet(include_ledger=True)
        self._summary.setText(
            "Tổng tồn cuối kỳ: " + format_money(sheet.total_closing_value)
            + ("    ✗ CÓ TỒN ÂM — KHÔNG THỂ LƯU" if any_manual_negative else "")
        )
        self._summary.setProperty("balanced", "false" if any_manual_negative else "true")
        self._summary.style().unpolish(self._summary)
        self._summary.style().polish(self._summary)
        self._btn_save.setEnabled(not any_manual_negative)

    def _set(self, row: int, col: int, text: str) -> None:
        item = self._table.item(row, col)
        if item is not None:
            item.setText(text)

    def _set_closing(self, row: int, col: int, text: str, negative: bool) -> None:
        item = self._table.item(row, col)
        if item is None:
            return
        item.setText(text)
        item.setForeground(_NEGATIVE if negative else QColor())
        font = item.font()
        font.setBold(negative)
        item.setFont(font)

    # ----- model in/out --------------------------------------------------

    def _cell(self, row: int, col: int) -> str:
        item = self._table.item(row, col)
        return item.text().strip() if item else ""

    def _num(self, row: int, col: int) -> Decimal:
        try:
            return parse_money(self._cell(row, col))
        except ValueError:
            return Decimal("0")

    def _line_at(self, row: int) -> ProductLine:
        code_item = self._table.item(row, _CODE)
        from_ledger = bool(code_item.data(Qt.UserRole)) if code_item else False
        return ProductLine(
            code=self._cell(row, _CODE),
            name=self._cell(row, _NAME),
            unit=self._cell(row, _UNIT),
            opening_price=self._num(row, _O_PRICE),
            opening_qty=self._num(row, _O_QTY),
            opening_value=self._num(row, _O_VAL),
            in_price=self._num(row, _I_PRICE),
            in_qty=self._num(row, _I_QTY),
            in_value=self._num(row, _I_VAL),
            out_price=self._num(row, _X_PRICE),
            out_qty=self._num(row, _X_QTY),
            out_value=self._num(row, _X_VAL),
            from_ledger=from_ledger,
        )

    def _sheet(self, include_ledger: bool = False) -> ProductSheet:
        lines = [self._line_at(r) for r in range(self._table.rowCount())]
        kept = [
            ln for ln in lines
            if not ln.is_empty and (include_ledger or not ln.from_ledger)
        ]
        return ProductSheet(period_key=period_key(), lines=kept)

    def _on_save(self) -> None:
        sheet = self._sheet(include_ledger=True)
        try:
            self._service.save(sheet)
        except ProductSheetError as exc:
            QMessageBox.warning(self, "Không thể lưu", str(exc))
            return
        self.reload()
        QMessageBox.information(
            self, "Đã lưu",
            f"Đã lưu bảng kê thành phẩm (155) cho kỳ {active_period().label}.\n"
            "Thành phẩm nhập tay đã được đồng bộ sang Nhập–Xuất–Tồn.",
        )
