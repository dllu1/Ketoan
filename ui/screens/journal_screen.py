"""JournalScreen: General Journal (Sổ nhật ký chung) — master/detail of entries."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
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

from data.repositories.journal_repo import JournalRepository
from domain.models.journal import EntryStatus, JournalEntry
from domain.money import format_money
from domain.services.journal_service import JournalService
from ui.modals.entry_modal import EntryModal
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.icon_input import IconInput

_STATUS_LABELS = {EntryStatus.DRAFT: "Nháp", EntryStatus.POSTED: "Đã ghi sổ"}


class JournalScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("JournalScreen")

        self._service = JournalService(JournalRepository())

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Sổ nhật ký chung")
        title.setObjectName("ScreenTitle")
        root.addWidget(title)

        toolbar = QHBoxLayout()
        self._search = IconInput(placeholder="Tìm theo số CT / diễn giải…", icon_name="search")
        self._search.text_changed.connect(lambda _: self._reload_entries())

        btn_new = Button("Bút toán mới", variant=ButtonVariant.PRIMARY, icon_name="plus")
        btn_new.clicked.connect(self._on_entry_new)
        btn_edit = Button("Sửa", icon_name="edit")
        btn_edit.clicked.connect(self._on_entry_edit)
        btn_delete = Button("Xóa", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_delete.clicked.connect(self._on_entry_delete)

        toolbar.addWidget(self._search, 1)
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

    def _reload_entries(self) -> None:
        query = self._search.text() if hasattr(self, "_search") else ""
        entries = self._service.search(query)
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
            self._reload_entries()

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
        for entry in self._service.list_all():
            if entry.id == entry_id:
                return entry
        return None

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
