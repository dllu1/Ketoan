"""JournalScreen: General Journal (Sổ nhật ký chung) — master/detail of entries."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
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
from data.repositories.account_repo import AccountRepository
from data.repositories.inventory_repo import InventoryRepository
from data.repositories.invoice_repo import InvoiceRepository
from data.repositories.item_repo import ItemRepository
from data.repositories.journal_repo import JournalRepository
from data.repositories.partner_repo import PartnerRepository
from domain.models.invoice import InvoiceKind
from domain.models.journal import EntryStatus, JournalEntry
from domain.money import format_money
from domain.services.inventory_service import InventoryService
from domain.services.journal_service import JournalService
from domain.services.purchase_service import PurchaseService
from domain.services.sales_service import SalesService
from ui.modals.entry_modal import EntryModal
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.icon_input import IconInput

_STATUS_LABELS = {EntryStatus.DRAFT: "Nháp", EntryStatus.POSTED: "Đã ghi sổ"}


class JournalScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("JournalScreen")

        self._service = JournalService(JournalRepository())

        # Optional invoice routing (số hóa đơn → Bán hàng / Mua hàng tab).
        inventory = InventoryService(InventoryRepository(), ItemRepository())
        invoice_repo = InvoiceRepository()
        partners = PartnerRepository()
        accounts = AccountRepository()
        self._sales = SalesService(invoice_repo, inventory, self._service, partners, accounts)
        self._purchase = PurchaseService(invoice_repo, inventory, self._service, partners, accounts)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Sổ nhật ký chung")
        title.setObjectName("ScreenTitle")
        root.addWidget(title)

        toolbar = QHBoxLayout()
        self._search = IconInput(placeholder="Tìm theo số CT / diễn giải…", icon_name="search")
        self._search.search_changed.connect(lambda _: self._reload_entries())

        # Chọn ngày tháng: lọc thêm bút toán theo khoảng ngày, khởi tạo theo
        # kỳ kế toán đang chọn.
        self._from = self._make_date()
        self._to = self._make_date()
        self._sync_dates_to_period()
        self._from.dateChanged.connect(lambda _: self._reload_entries())
        self._to.dateChanged.connect(lambda _: self._reload_entries())

        btn_new = Button("Bút toán mới", variant=ButtonVariant.PRIMARY, icon_name="plus")
        btn_new.clicked.connect(self._on_entry_new)
        btn_edit = Button("Sửa", icon_name="edit")
        btn_edit.clicked.connect(self._on_entry_edit)
        btn_delete = Button("Xóa", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_delete.clicked.connect(self._on_entry_delete)

        toolbar.addWidget(self._search, 1)
        toolbar.addWidget(QLabel("Từ"))
        toolbar.addWidget(self._from)
        toolbar.addWidget(QLabel("đến"))
        toolbar.addWidget(self._to)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(btn_delete)
        toolbar.addWidget(btn_new)
        root.addLayout(toolbar)

        self._entry_table = QTableWidget(0, 5)
        self._entry_table.setHorizontalHeaderLabels(
            ["Ngày", "Số CT", "Diễn giải", "Tổng tiền", "Trạng thái"]
        )
        self._configure_table(self._entry_table)
        self._entry_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._entry_table.currentCellChanged.connect(lambda *_: self._show_lines())
        self._entry_table.itemDoubleClicked.connect(lambda *_: self._on_entry_edit())
        root.addWidget(self._entry_table, 3)

        lines_label = QLabel("Dòng bút toán (Nợ / Có)")
        lines_label.setObjectName("SectionLabel")
        root.addWidget(lines_label)

        self._line_table = QTableWidget(0, 5)
        self._line_table.setHorizontalHeaderLabels(
            ["TK", "Tên tài khoản", "Diễn giải", "Nợ", "Có"]
        )
        self._configure_table(self._line_table)
        self._line_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        root.addWidget(self._line_table, 2)

        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_entry_new)

        self._reload_entries()

    # ----- entries ------------------------------------------------------

    def on_activated(self) -> None:
        self._sync_dates_to_period()
        self._reload_entries()

    def _reload_entries(self) -> None:
        query = self._search.text() if hasattr(self, "_search") else ""
        period = active_period()
        start, end = self._date_range()
        entries = [
            e for e in self._service.search(query)
            if period.matches(e.entry_date) and start <= e.entry_date <= end
        ]
        # Cache theo id để chọn dòng không phải nạp lại toàn bộ sổ từ DB mỗi lần
        # đổi ô (currentCellChanged bắn liên tục khi dùng phím mũi tên).
        self._entries_by_id = {e.id: e for e in entries}
        self._entry_table.setRowCount(0)
        for entry in entries:
            row = self._entry_table.rowCount()
            self._entry_table.insertRow(row)
            cells = [
                entry.entry_date.strftime("%d/%m/%Y"),
                entry.ref,
                entry.description,
                format_money(entry.total_debit),
                _STATUS_LABELS.get(entry.status, entry.status.value),
            ]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.UserRole, entry.id)
                if col == 3:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._entry_table.setItem(row, col, item)
        self._show_lines()

    def _show_lines(self) -> None:
        entry = self._selected_entry()
        self._line_table.setRowCount(0)
        if entry is None:
            return
        for line in entry.lines:
            row = self._line_table.rowCount()
            self._line_table.insertRow(row)
            cells = [
                line.account_code,
                line.account_name,
                line.description,
                format_money(line.debit) if line.debit else "",
                format_money(line.credit) if line.credit else "",
            ]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col in (3, 4):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._line_table.setItem(row, col, item)

    def _on_entry_new(self) -> None:
        dialog = EntryModal(self)
        if dialog.exec():
            try:
                self._service.create(dialog.entry())
            except Exception as exc:
                QMessageBox.warning(self, "Không thể lưu", str(exc))
                return
            self._route_invoice(dialog)
            self._reload_entries()

    def _on_entry_edit(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        dialog = EntryModal(self, entry=entry)
        if dialog.exec():
            try:
                self._service.update(dialog.entry())
            except Exception as exc:
                QMessageBox.warning(self, "Không thể lưu", str(exc))
                return
            self._route_invoice(dialog)
            self._reload_entries()

    def _route_invoice(self, dialog: EntryModal) -> None:
        """Auto-file an optional invoice into the Bán hàng / Mua hàng tab.

        Saved as a draft document; the journal entry above is the accounting
        record. Failure here must not lose the already-saved bút toán, so it is
        surfaced as a warning rather than raised.
        """
        request = dialog.invoice_request()
        if request is None:
            return
        invoice, kind = request
        service = self._sales if kind is InvoiceKind.SALE else self._purchase
        try:
            service.create(invoice)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Bút toán đã lưu — chưa tạo được hóa đơn",
                f"Hóa đơn '{invoice.invoice_no}' không được tạo:\n{exc}",
            )

    def _on_entry_delete(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        confirm = QMessageBox.question(
            self, "Xóa bút toán", f"Xóa bút toán '{entry.ref}'?"
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._service.delete(entry.id)
        except Exception as exc:
            QMessageBox.warning(self, "Không thể xóa", str(exc))
            return
        self._reload_entries()

    def _selected_entry(self) -> JournalEntry | None:
        row = self._entry_table.currentRow()
        if row < 0:
            return None
        item = self._entry_table.item(row, 0)
        if item is None:
            return None
        entry_id = item.data(Qt.UserRole)
        return getattr(self, "_entries_by_id", {}).get(entry_id)

    # ----- date range ---------------------------------------------------

    @staticmethod
    def _make_date() -> QDateEdit:
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("dd/MM/yyyy")
        return edit

    def _sync_dates_to_period(self) -> None:
        """Reset the From/To pickers to the active period's bounds.

        Signals are blocked so resyncing on period change doesn't fire an extra
        reload (the caller reloads once afterwards).
        """
        period = active_period()
        if period.month is None:
            start, end = date(period.year, 1, 1), date(period.year, 12, 31)
        else:
            start = date(period.year, period.month, 1)
            next_month = date(
                period.year + (period.month == 12), period.month % 12 + 1, 1
            )
            end = next_month - timedelta(days=1)
        for widget, value in ((self._from, start), (self._to, end)):
            blocked = widget.blockSignals(True)
            widget.setDate(QDate(value.year, value.month, value.day))
            widget.blockSignals(blocked)

    def _date_range(self) -> tuple[date, date]:
        start = self._from.date()
        end = self._to.date()
        return (
            date(start.year(), start.month(), start.day()),
            date(end.year(), end.month(), end.day()),
        )

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
