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
from domain.services.item_service import ItemService
from ui.modals.item_detail_modal import ItemDetailModal
from ui.modals.item_import_modal import ItemImportModal
from ui.modals.stock_modal import StockModal
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.date_edit import DateEdit
from ui.primitives.icon_input import IconInput
from ui.primitives.segmented import Segmented
from ui.screens.costing_view import CostingView
from ui.screens.material_cost_view import MaterialCostView
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
                ("nvl_direct", "NVL trực tiếp (15401)"),
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
        self._nvl_direct = MaterialCostView()
        self._costing = CostingView()
        self._product = ProductSheetView()
        self._pages: dict[str, QWidget] = {
            "nxt": self._nxt,
            "material": self._material,
            "nvl_direct": self._nvl_direct,
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
        self._items = ItemService(ItemRepository())

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

        # DateEdit: bôi đen + Delete để xóa trắng rồi gõ tay cả ngày/tháng/năm.
        self._date_from = DateEdit(value=QDate(QDate.currentDate().year(), 1, 1))
        self._date_from.dateChanged.connect(lambda _: self._reload())

        self._date_to = DateEdit()
        self._date_to.dateChanged.connect(lambda _: self._reload())

        btn_to_catalog = Button("Nhập vào danh mục", icon_name="download")
        btn_to_catalog.setToolTip(
            "Chọn mặt hàng đang có trong kho để đưa vào Danh mục vật tư "
            "(có tích chọn từng mã, không nhập cả kho)."
        )
        btn_to_catalog.clicked.connect(self._on_import_to_catalog)
        btn_delete = Button("Xóa khỏi kho", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_delete.setToolTip(
            "Xóa hẳn (các) mặt hàng đang chọn khỏi kho — bỏ toàn bộ bút toán "
            "nhập–xuất của chúng. Giữ Ctrl/Shift để chọn nhiều dòng."
        )
        btn_delete.clicked.connect(self._on_delete_items)
        btn_in = Button("Nhập kho", variant=ButtonVariant.PRIMARY, icon_name="arrow-down")
        btn_in.clicked.connect(self._on_stock_in)

        toolbar.addWidget(self._search, 1)
        toolbar.addWidget(QLabel("Mã kho"))
        toolbar.addWidget(self._account)
        toolbar.addWidget(QLabel("Từ"))
        toolbar.addWidget(self._date_from)
        toolbar.addWidget(QLabel("đến"))
        toolbar.addWidget(self._date_to)
        toolbar.addWidget(btn_to_catalog)
        toolbar.addWidget(btn_delete)
        toolbar.addWidget(btn_in)
        root.addLayout(toolbar)

        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # ExtendedSelection: giữ Ctrl/Shift để chọn nhiều mặt hàng cần xóa.
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # Double-click một mặt hàng = mở chi tiết (sổ phát sinh của riêng nó).
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        root.addWidget(self._table, 1)

        # Dòng bảng → dòng NXT tương ứng (dòng tiêu đề nhóm / cộng nhóm không có).
        self._rows_by_table_row: dict[int, object] = {}

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
        self._rows_by_table_row.clear()

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

        total_open = total_in = total_out = total_close = Decimal("0")
        for account in sorted(groups):
            self._add_section_row(self._account_label(account))
            group_open = group_in = group_out = group_close = Decimal("0")
            for r in groups[account]:
                self._add_item_row(r)
                group_open += r.opening_value
                group_in += r.in_value
                group_out += r.out_value
                group_close += r.closing_value
            self._add_group_total_row(
                account, group_open, group_in, group_out, group_close
            )
            total_open += group_open
            total_in += group_in
            total_out += group_out
            total_close += group_close
        if len(groups) > 1:
            # Nhiều nhóm kho cùng hiện → cộng chung để khỏi nhẩm các dòng "Cộng
            # nhóm". Lọc về một nhóm thì dòng cộng nhóm đã chính là tổng.
            self._add_group_total_row(
                "", total_open, total_in, total_out, total_close,
                label="TỔNG CỘNG",
            )
        self._summary.setText(
            f"Cộng:  Đầu kỳ {format_money(total_open)}"
            f"    Nhập {format_money(total_in)}"
            f"    Xuất {format_money(total_out)}"
            f"    Tồn cuối kỳ {format_money(total_close)}"
        )

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
        self._rows_by_table_row[row] = r
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
        out_value: Decimal, closing_value: Decimal, *, label: str = "",
    ) -> None:
        """Dòng cộng nhóm: chỉ cộng cột tổng tiền (SL/ĐG khác ĐVT nên không cộng).

        ``label`` ghi đè nhãn để dùng lại cho dòng tổng cộng toàn bảng.
        """
        row = self._table.rowCount()
        self._table.insertRow(row)
        cells = [""] * len(_HEADERS)
        cells[_C_NAME] = label or (f"Cộng nhóm {account}" if account else "Cộng nhóm")
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

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        """Mở chi tiết mặt hàng; bỏ qua dòng tiêu đề nhóm và dòng cộng nhóm."""
        nxt_row = self._rows_by_table_row.get(row)
        if nxt_row is None:
            return
        period = (
            f"{self._date_from.date().toString('dd/MM/yyyy')}"
            f"–{self._date_to.date().toString('dd/MM/yyyy')}"
        )
        ItemDetailModal(
            self, item_code=nxt_row.item_code, nxt_row=nxt_row, period_label=period
        ).exec()

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

    def _selected_item_codes(self) -> list[tuple[str, str]]:
        """(mã, tên) của các mặt hàng đang chọn (bỏ dòng tiêu đề nhóm / cộng nhóm)."""
        seen: dict[str, str] = {}
        for index in self._table.selectionModel().selectedRows():
            nxt_row = self._rows_by_table_row.get(index.row())
            if nxt_row is not None:
                seen.setdefault(nxt_row.item_code, nxt_row.item_name)
        return list(seen.items())

    def _on_delete_items(self) -> None:
        selected = self._selected_item_codes()
        if not selected:
            QMessageBox.information(
                self, "Chưa chọn mặt hàng",
                "Hãy chọn ít nhất một mặt hàng trong bảng để xóa. "
                "Giữ Ctrl hoặc Shift để chọn nhiều dòng cùng lúc.",
            )
            return
        preview = "\n".join(f"•  {code} — {name}" for code, name in selected[:15])
        if len(selected) > 15:
            preview += f"\n… và {len(selected) - 15} mặt hàng khác"
        confirm = QMessageBox.question(
            self, "Xóa khỏi kho",
            f"Xóa hẳn {len(selected)} mặt hàng sau khỏi kho?\n\n{preview}\n\n"
            "Toàn bộ bút toán nhập–xuất của các mặt hàng này sẽ bị xóa và không "
            "thể hoàn tác.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        removed = self._service.remove_items([code for code, _name in selected])
        self._reload()
        QMessageBox.information(
            self, "Đã xóa",
            f"Đã xóa {len(selected)} mặt hàng khỏi kho ({removed} bút toán nhập–xuất).",
        )

    def _on_import_to_catalog(self) -> None:
        """Chọn mặt hàng trong kho để đưa vào Danh mục (có kiểm soát từng mã)."""
        rows = self._service.compute_nxt(
            self._qdate(self._date_from), self._qdate(self._date_to)
        )
        if not rows:
            QMessageBox.information(
                self, "Kho trống",
                "Chưa có mặt hàng nào trong kho (theo kỳ đang lọc) để đưa vào danh mục.",
            )
            return
        existing = {i.code for i in self._items.list_all()}
        candidates = [
            (r.item_code, r.item_name, r.unit, r.account_code, r.item_code in existing)
            for r in rows
        ]
        if all(exists for *_x, exists in candidates):
            QMessageBox.information(
                self, "Không có mặt hàng mới",
                "Mọi mặt hàng trong kho đều đã có trong danh mục.",
            )
            return
        dialog = ItemImportModal(self, candidates=candidates)
        if not dialog.exec():
            return
        created = self._items.import_stock_items(dialog.selected())
        QMessageBox.information(
            self, "Đã nhập vào danh mục",
            f"Đã thêm {created} mặt hàng vào Danh mục vật tư.",
        )

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
    def _qdate(widget: DateEdit) -> date:
        return widget.date_value()
