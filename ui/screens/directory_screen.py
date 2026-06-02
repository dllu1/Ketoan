"""Directory screen: Partner + Item management (Phase 1)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from data.repositories.account_repo import AccountRepository
from data.repositories.item_repo import ItemRepository
from data.repositories.partner_repo import PartnerRepository
from domain.models.account import Account
from domain.models.item import Item
from domain.models.partner import Partner
from domain.services.account_service import AccountService
from domain.services.item_service import ItemService
from domain.services.partner_service import PartnerService
from ui.modals.account_modal import AccountModal
from ui.modals.item_modal import ItemModal
from ui.modals.partner_modal import PartnerModal
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.icon_input import IconInput


class DirectoryScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DirectoryScreen")

        self._partner_service = PartnerService(PartnerRepository())
        self._item_service = ItemService(ItemRepository())
        self._account_service = AccountService(AccountRepository())

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Danh mục")
        title.setObjectName("ScreenTitle")
        root.addWidget(title)

        tabs = QTabWidget()
        tabs.setObjectName("DirectoryTabs")
        tabs.addTab(self._build_partner_tab(), "Đối tác (KH/NCC)")
        tabs.addTab(self._build_item_tab(), "Vật tư / Hàng hóa")
        tabs.addTab(self._build_account_tab(), "Hệ thống tài khoản")
        root.addWidget(tabs, 1)

        self._reload_partners()
        self._reload_items()
        self._reload_accounts()

    # ----- Partners ----------------------------------------------------------

    def _build_partner_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self._partner_search = IconInput(
            placeholder="Tìm theo mã / tên / MST…",
            icon_name="search",
        )
        self._partner_search.text_changed.connect(lambda _: self._reload_partners())

        btn_new = Button("Đối tác mới", variant=ButtonVariant.PRIMARY, icon_name="plus")
        btn_new.clicked.connect(self._on_partner_new)

        btn_edit = Button("Sửa", icon_name="edit")
        btn_edit.clicked.connect(self._on_partner_edit)

        toolbar.addWidget(self._partner_search, 1)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_new)
        layout.addLayout(toolbar)

        self._partner_table = QTableWidget(0, 6)
        self._partner_table.setHorizontalHeaderLabels(
            ["Mã", "Tên đối tác", "Loại", "MST", "Điện thoại", "Email"]
        )
        self._configure_table(self._partner_table)
        self._partner_table.itemDoubleClicked.connect(lambda *_: self._on_partner_edit())
        layout.addWidget(self._partner_table, 1)

        return widget

    def _reload_partners(self) -> None:
        query = self._partner_search.text() if hasattr(self, "_partner_search") else ""
        partners = self._partner_service.search(query)
        self._partner_table.setRowCount(0)
        for partner in partners:
            row = self._partner_table.rowCount()
            self._partner_table.insertRow(row)
            cells = [
                partner.code,
                partner.name,
                partner.type.value,
                partner.tax_code,
                partner.phone,
                partner.email,
            ]
            for col, value in enumerate(cells):
                table_item = QTableWidgetItem(value)
                table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
                if col == 0:
                    table_item.setData(Qt.UserRole, partner.id)
                self._partner_table.setItem(row, col, table_item)

    def _on_partner_new(self) -> None:
        dialog = PartnerModal(self)
        if dialog.exec():
            try:
                self._partner_service.create(dialog.partner())
            except Exception as exc:
                QMessageBox.warning(self, "Không thể lưu", str(exc))
                return
            self._reload_partners()

    def _on_partner_edit(self) -> None:
        partner = self._selected_partner()
        if partner is None:
            return
        dialog = PartnerModal(self, partner=partner)
        if dialog.exec():
            try:
                self._partner_service.update(dialog.partner())
            except Exception as exc:
                QMessageBox.warning(self, "Không thể lưu", str(exc))
                return
            self._reload_partners()

    def _selected_partner(self) -> Partner | None:
        row = self._partner_table.currentRow()
        if row < 0:
            return None
        partner_id = self._partner_table.item(row, 0).data(Qt.UserRole)
        for p in self._partner_service.list_all():
            if p.id == partner_id:
                return p
        return None

    # ----- Items -------------------------------------------------------------

    def _build_item_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self._item_search = IconInput(
            placeholder="Tìm theo mã / tên vật tư…",
            icon_name="search",
        )
        self._item_search.text_changed.connect(lambda _: self._reload_items())

        btn_new = Button("Vật tư mới", variant=ButtonVariant.PRIMARY, icon_name="plus")
        btn_new.clicked.connect(self._on_item_new)

        btn_edit = Button("Sửa", icon_name="edit")
        btn_edit.clicked.connect(self._on_item_edit)

        toolbar.addWidget(self._item_search, 1)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_new)
        layout.addLayout(toolbar)

        self._item_table = QTableWidget(0, 6)
        self._item_table.setHorizontalHeaderLabels(
            ["Mã", "Tên", "Nhóm (TK)", "ĐVT", "Đơn giá", "VAT %"]
        )
        self._configure_table(self._item_table)
        self._item_table.itemDoubleClicked.connect(lambda *_: self._on_item_edit())
        layout.addWidget(self._item_table, 1)

        return widget

    def _reload_items(self) -> None:
        query = self._item_search.text() if hasattr(self, "_item_search") else ""
        items = self._item_service.search(query)
        self._item_table.setRowCount(0)
        for item in items:
            row = self._item_table.rowCount()
            self._item_table.insertRow(row)
            cells = [
                item.code,
                item.name,
                item.category.value,
                item.unit,
                f"{item.unit_price:,.0f}",
                f"{item.vat_rate}",
            ]
            for col, value in enumerate(cells):
                table_item = QTableWidgetItem(value)
                table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
                if col == 0:
                    table_item.setData(Qt.UserRole, item.id)
                if col in (4, 5):
                    table_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._item_table.setItem(row, col, table_item)

    def _on_item_new(self) -> None:
        dialog = ItemModal(self)
        if dialog.exec():
            try:
                self._item_service.create(dialog.item())
            except Exception as exc:
                QMessageBox.warning(self, "Không thể lưu", str(exc))
                return
            self._reload_items()

    def _on_item_edit(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        dialog = ItemModal(self, item=item)
        if dialog.exec():
            try:
                self._item_service.update(dialog.item())
            except Exception as exc:
                QMessageBox.warning(self, "Không thể lưu", str(exc))
                return
            self._reload_items()

    def _selected_item(self) -> Item | None:
        row = self._item_table.currentRow()
        if row < 0:
            return None
        item_id = self._item_table.item(row, 0).data(Qt.UserRole)
        for i in self._item_service.list_all():
            if i.id == item_id:
                return i
        return None

    # ----- Accounts ----------------------------------------------------------

    def _build_account_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        self._account_search = IconInput(
            placeholder="Tìm theo mã / tên tài khoản…",
            icon_name="search",
        )
        self._account_search.text_changed.connect(lambda _: self._reload_accounts())

        btn_new = Button("Tài khoản mới", variant=ButtonVariant.PRIMARY, icon_name="plus")
        btn_new.clicked.connect(self._on_account_new)

        btn_edit = Button("Sửa", icon_name="edit")
        btn_edit.clicked.connect(self._on_account_edit)

        toolbar.addWidget(self._account_search, 1)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_new)
        layout.addLayout(toolbar)

        self._account_table = QTableWidget(0, 4)
        self._account_table.setHorizontalHeaderLabels(
            ["Mã", "Tên tài khoản", "Loại", "Nguồn (TT)"]
        )
        self._configure_table(self._account_table)
        self._account_table.itemDoubleClicked.connect(lambda *_: self._on_account_edit())
        layout.addWidget(self._account_table, 1)

        return widget

    def _reload_accounts(self) -> None:
        query = self._account_search.text() if hasattr(self, "_account_search") else ""
        accounts = self._account_service.search(query)
        self._account_table.setRowCount(0)
        for account in accounts:
            row = self._account_table.rowCount()
            self._account_table.insertRow(row)
            cells = [account.code, account.name, account.kind, account.circular]
            for col, value in enumerate(cells):
                table_item = QTableWidgetItem(value)
                table_item.setFlags(table_item.flags() & ~Qt.ItemIsEditable)
                if col == 0:
                    table_item.setData(Qt.UserRole, account.id)
                self._account_table.setItem(row, col, table_item)

    def _on_account_new(self) -> None:
        dialog = AccountModal(self)
        if dialog.exec():
            try:
                self._account_service.create(dialog.account())
            except Exception as exc:
                QMessageBox.warning(self, "Không thể lưu", str(exc))
                return
            self._reload_accounts()

    def _on_account_edit(self) -> None:
        account = self._selected_account()
        if account is None:
            return
        dialog = AccountModal(self, account=account)
        if dialog.exec():
            try:
                self._account_service.update(dialog.account())
            except Exception as exc:
                QMessageBox.warning(self, "Không thể lưu", str(exc))
                return
            self._reload_accounts()

    def _selected_account(self) -> Account | None:
        row = self._account_table.currentRow()
        if row < 0:
            return None
        account_id = self._account_table.item(row, 0).data(Qt.UserRole)
        for a in self._account_service.list_all():
            if a.id == account_id:
                return a
        return None

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
