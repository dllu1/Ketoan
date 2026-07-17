"""Kho hàng module: three tabs sharing the inventory area.

* "Nhập–Xuất–Tồn"      — the live, ledger-derived NXT report (:class:`_NxtView`,
                          unchanged behaviour from before this module grew tabs).
* "Bảng kê NVL chính"  — editable raw-material worksheet with the negative-stock
                          guard (:class:`MaterialSheetView`).
* "Giá thành SP"        — editable product-costing worksheet (:class:`CostingView`).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from data.repositories.inventory_repo import InventoryRepository
from data.repositories.item_repo import ItemRepository
from domain.money import format_money
from domain.services.inventory_service import InventoryError, InventoryService
from ui.modals.stock_modal import StockModal
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.icon_input import IconInput
from ui.primitives.segmented import Segmented
from ui.screens.costing_view import CostingView
from ui.screens.material_sheet_view import MaterialSheetView
from ui.screens.product_sheet_view import ProductSheetView
from ui.tokens import active_tokens

_ACCOUNT_LABELS = {
    "": "Tất cả nhóm",
    "152": "152 — Nguyên vật liệu",
    "153": "153 — Công cụ, dụng cụ",
    "155": "155 — Thành phẩm",
    "156": "156 — Hàng hóa",
}

_HEADERS = [
    "Mã hàng", "Tên hàng", "ĐVT",
    "ĐK·ĐG", "ĐK·SL", "ĐK·TT",
    "Nhập·ĐG", "Nhập·SL", "Nhập·TT",
    "Xuất·ĐG", "Xuất·SL", "Xuất·TT",
    "Tồn·ĐG", "Tồn·SL", "Tồn·TT",
]
(_C_CODE, _C_NAME, _C_UNIT,
 _C_O_PRICE, _C_O_QTY, _C_O_VAL,
 _C_I_PRICE, _C_I_QTY, _C_I_VAL,
 _C_X_PRICE, _C_X_QTY, _C_X_VAL,
 _C_C_PRICE, _C_C_QTY, _C_C_VAL) = range(15)


class InventoryScreen(QWidget):
    """Tabbed container: NXT report + the two editable worksheets."""

    # Forwarded from the NXT tab (vd: mở Danh mục để thêm vật tư).
    navigate_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("InventoryScreen")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Kho hàng")
        title.setObjectName("ScreenTitle")
        root.addWidget(title)

        self._switcher = Segmented(
            [
                ("nxt", "Nhập–Xuất–Tồn"),
                ("material", "Bảng kê NVL chính"),
                ("costing", "Giá thành SP"),
                ("product", "Bảng kê TP (155)"),
            ],
            default="nxt",
        )
        self._switcher.selection_changed.connect(self._on_switch)
        switch_row = QHBoxLayout()
        switch_row.addWidget(self._switcher)
        switch_row.addStretch(1)
        root.addLayout(switch_row)

        self._nxt = _NxtView()
        self._nxt.navigate_requested.connect(self.navigate_requested)
        self._material = MaterialSheetView()
        self._costing = CostingView()
        self._product = ProductSheetView()
        self._pages: dict[str, QWidget] = {
            "nxt": self._nxt,
            "material": self._material,
            "costing": self._costing,
            "product": self._product,
        }

        self._stack = QStackedWidget()
        for page in self._pages.values():
            self._stack.addWidget(page)
        root.addWidget(self._stack, 1)

    def _on_switch(self, key: str) -> None:
        page = self._pages.get(key)
        if page is not None:
            self._stack.setCurrentWidget(page)
            self._reload_current()

    def _reload_current(self) -> None:
        page = self._stack.currentWidget()
        reload_fn = getattr(page, "reload", None)
        if callable(reload_fn):
            reload_fn()

    def on_activated(self) -> None:
        """Refresh the visible tab when the module is shown or the period changes."""
        self._reload_current()


class _NxtView(QWidget):
    """Ledger-derived Nhập–Xuất–Tồn report (read-only)."""

    navigate_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("NxtView")

        self._service = InventoryService(InventoryRepository(), ItemRepository())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        toolbar = QHBoxLayout()
        self._search = IconInput(placeholder="Tìm theo mã / tên hàng…", icon_name="search")
        self._search.search_changed.connect(lambda _: self._reload())

        self._account = QComboBox()
        for code, label in _ACCOUNT_LABELS.items():
            self._account.addItem(label, code)
        self._account.currentIndexChanged.connect(lambda _: self._reload())

        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat("dd/MM/yyyy")
        self._date_from.setDate(QDate(QDate.currentDate().year(), 1, 1))
        self._date_from.dateChanged.connect(lambda _: self._reload())

        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDisplayFormat("dd/MM/yyyy")
        self._date_to.setDate(QDate.currentDate())
        self._date_to.dateChanged.connect(lambda _: self._reload())

        btn_in = Button("Nhập kho", variant=ButtonVariant.PRIMARY, icon_name="arrow-down")
        btn_in.clicked.connect(self._on_stock_in)

        toolbar.addWidget(self._search, 1)
        toolbar.addWidget(QLabel("Mã kho"))
        toolbar.addWidget(self._account)
        toolbar.addWidget(QLabel("Từ"))
        toolbar.addWidget(self._date_from)
        toolbar.addWidget(QLabel("đến"))
        toolbar.addWidget(self._date_to)
        toolbar.addWidget(btn_in)
        root.addLayout(toolbar)

        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        root.addWidget(self._table, 1)

        self._summary = QLabel()
        self._summary.setObjectName("BalanceBar")
        self._summary.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        root.addWidget(self._summary)

        self._reload()

    # ----- data ---------------------------------------------------------

    def reload(self) -> None:
        self._reload()

    def _reload(self) -> None:
        date_from = self._qdate(self._date_from)
        date_to = self._qdate(self._date_to)
        account_filter = self._account.currentData()
        query = self._search.text().strip().lower() if hasattr(self, "_search") else ""

        rows = self._service.compute_nxt(date_from, date_to)
        self._table.setRowCount(0)
        self._table.clearSpans()

        kept = [
            r for r in rows
            if not (account_filter and r.account_code != account_filter)
            and not (query and query not in r.item_code.lower()
                     and query not in r.item_name.lower())
        ]
        # Phân mục theo tài khoản kho (152 / 153 / 155 / 156 …).
        groups: dict[str, list] = {}
        for r in kept:
            groups.setdefault(r.account_code, []).append(r)

        total_closing_value = Decimal("0")
        for account in sorted(groups):
            self._add_section_row(self._account_label(account))
            group_open = group_in = group_out = group_close = Decimal("0")
            for r in groups[account]:
                self._add_item_row(r)
                group_open += r.opening_value
                group_in += r.in_value
                group_out += r.out_value
                group_close += r.closing_value
                total_closing_value += r.closing_value
            self._add_group_total_row(
                account, group_open, group_in, group_out, group_close
            )
        self._summary.setText(f"Tổng giá trị tồn cuối kỳ: {format_money(total_closing_value)}")

    @staticmethod
    def _account_label(account: str) -> str:
        if account and account in _ACCOUNT_LABELS:
            return _ACCOUNT_LABELS[account]
        if account:
            return f"{account} — Nhóm khác"
        return "Chưa phân nhóm tài khoản kho"

    def _add_section_row(self, label: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        item = QTableWidgetItem(label)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setForeground(QColor(active_tokens().brand))
        self._table.setItem(row, 0, item)
        self._table.setSpan(row, 0, 1, len(_HEADERS))

    def _add_item_row(self, r) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        cells = [
            r.item_code,
            r.item_name,
            r.unit,
            format_money(r.opening_price), self._qty(r.opening_qty),
            format_money(r.opening_value),
            format_money(r.in_price), self._qty(r.in_qty),
            format_money(r.in_value),
            format_money(r.out_price), self._qty(r.out_qty),
            format_money(r.out_value),
            format_money(r.closing_price), self._qty(r.closing_qty),
            format_money(r.closing_value),
        ]
        for col, value in enumerate(cells):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if col >= 3:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, col, item)

    def _add_group_total_row(
        self, account: str, open_value: Decimal, in_value: Decimal,
        out_value: Decimal, closing_value: Decimal,
    ) -> None:
        """Dòng cộng nhóm: chỉ cộng cột tổng tiền (SL/ĐG khác ĐVT nên không cộng)."""
        row = self._table.rowCount()
        self._table.insertRow(row)
        cells = [""] * len(_HEADERS)
        cells[_C_NAME] = f"Cộng nhóm {account}" if account else "Cộng nhóm"
        cells[_C_O_VAL] = format_money(open_value)
        cells[_C_I_VAL] = format_money(in_value)
        cells[_C_X_VAL] = format_money(out_value)
        cells[_C_C_VAL] = format_money(closing_value)
        for col, value in enumerate(cells):
            item = QTableWidgetItem(value)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            if col >= 3:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, col, item)

    def _on_stock_in(self) -> None:
        dialog = StockModal(self)
        if not dialog.has_items:
            self._prompt_add_items()
            return
        if not dialog.exec():
            return
        if dialog.quantity() <= 0:
            QMessageBox.warning(self, "Không thể lưu", "Số lượng phải lớn hơn 0.")
            return
        try:
            self._service.record_in(
                dialog.item_code(), dialog.quantity(), dialog.unit_cost(),
                move_date=dialog.move_date(), kind=dialog.kind(), note=dialog.note(),
            )
        except InventoryError as exc:
            QMessageBox.warning(self, "Không thể lưu", str(exc))
            return
        self._reload()

    def _prompt_add_items(self) -> None:
        """No catalog items yet: explain how to add one and offer a shortcut."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("Chưa có vật tư")
        box.setText("Kho chưa có vật tư / hàng hóa nào để nhập.")
        box.setInformativeText(
            "Trước tiên hãy khai báo mặt hàng trong <b>Danh mục → Vật tư &amp; Hàng hóa</b> "
            "(nút <b>“Thêm hàng hóa”</b>), sau đó quay lại đây để nhập kho."
        )
        open_btn = box.addButton("Mở Danh mục →", QMessageBox.AcceptRole)
        box.addButton("Để sau", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            self.navigate_requested.emit("directory")

    @staticmethod
    def _qty(value: Decimal) -> str:
        return f"{value:,.2f}".rstrip("0").rstrip(".") if value else "0"

    @staticmethod
    def _qdate(widget: QDateEdit) -> date:
        qd = widget.date()
        return date(qd.year(), qd.month(), qd.day())
