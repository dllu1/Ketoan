"""EntryModal: create / edit a balanced journal entry (bút toán Nợ/Có)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from data.repositories.account_repo import AccountRepository
from domain.models.journal import EntryStatus, JournalEntry, JournalLine
from domain.money import format_money, parse_money
from ui.primitives.button import Button, ButtonVariant
from ui.tokens import Tokens

_COL_CODE, _COL_DESC, _COL_DEBIT, _COL_CREDIT = range(4)


class _AccountDelegate(QStyledItemDelegate):
    """Editor for the TK column sharing a single completer/model."""

    def __init__(self, completer: QCompleter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._completer = completer

    def createEditor(self, parent, option, index):  # noqa: N802 (Qt signature)
        editor = QLineEdit(parent)
        editor.setCompleter(self._completer)
        return editor


class EntryModal(QDialog):
    def __init__(self, parent: QWidget | None = None, *, entry: JournalEntry | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EntryModal")
        self.setModal(True)
        self.setMinimumWidth(640)
        self.setWindowTitle("Bút toán mới" if entry is None else f"Sửa: {entry.ref}")

        self._original = entry
        self._tokens = Tokens()
        self._status = EntryStatus.POSTED

        accounts = AccountRepository().list_all()
        self._account_names = {a.code: a.name for a in accounts}
        completer = QCompleter([a.code for a in accounts], self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)

        # ----- metadata --------------------------------------------------
        self._ref = QLineEdit()
        self._date = QDateEdit()
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("dd/MM/yyyy")
        self._date.setDate(QDate.currentDate())
        self._description = QLineEdit()

        form = QFormLayout()
        form.addRow("Số CT *", self._ref)
        form.addRow("Ngày", self._date)
        form.addRow("Diễn giải", self._description)

        # ----- lines grid ------------------------------------------------
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["TK", "Diễn giải", "Nợ", "Có"])
        self._table.setItemDelegateForColumn(_COL_CODE, _AccountDelegate(completer, self))
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(_COL_DESC, QHeaderView.Stretch)
        header.setSectionResizeMode(_COL_CODE, QHeaderView.ResizeToContents)
        self._table.itemChanged.connect(lambda *_: self._recompute_balance())

        line_buttons = QHBoxLayout()
        btn_add = Button("+ Thêm dòng", icon_name="plus")
        btn_add.clicked.connect(lambda: self._add_row())
        btn_del = Button("− Xóa dòng", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_del.clicked.connect(self._remove_current_row)
        line_buttons.addWidget(btn_add)
        line_buttons.addWidget(btn_del)
        line_buttons.addStretch(1)

        # ----- balance bar ----------------------------------------------
        self._balance_label = QLabel()
        self._balance_label.setObjectName("BalanceBar")

        # ----- footer ----------------------------------------------------
        footer = QHBoxLayout()
        btn_cancel = Button("Hủy")
        btn_cancel.clicked.connect(self.reject)
        btn_draft = Button("Lưu nháp", icon_name="edit")
        btn_draft.clicked.connect(lambda: self._submit(EntryStatus.DRAFT))
        btn_post = Button("Ghi sổ", variant=ButtonVariant.PRIMARY, icon_name="check")
        btn_post.clicked.connect(lambda: self._submit(EntryStatus.POSTED))
        footer.addStretch(1)
        footer.addWidget(btn_cancel)
        footer.addWidget(btn_draft)
        footer.addWidget(btn_post)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._table, 1)
        layout.addLayout(line_buttons)
        layout.addWidget(self._balance_label)
        layout.addLayout(footer)

        if entry is not None:
            self._populate(entry)
            self._ref.setReadOnly(True)
        else:
            self._add_row()
            self._add_row()
        self._recompute_balance()

    # ----- row helpers --------------------------------------------------

    def _add_row(self, line: JournalLine | None = None) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        values = [
            line.account_code if line else "",
            line.description if line else "",
            format_money(line.debit) if line and line.debit else "",
            format_money(line.credit) if line and line.credit else "",
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col in (_COL_DEBIT, _COL_CREDIT):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, col, item)

    def _remove_current_row(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)
            self._recompute_balance()

    def _cell_text(self, row: int, col: int) -> str:
        item = self._table.item(row, col)
        return item.text().strip() if item else ""

    def _cell_money(self, row: int, col: int) -> Decimal:
        try:
            return parse_money(self._cell_text(row, col))
        except ValueError:
            return Decimal("0")

    # ----- balance ------------------------------------------------------

    def _recompute_balance(self) -> None:
        total_debit = sum(
            (self._cell_money(r, _COL_DEBIT) for r in range(self._table.rowCount())),
            Decimal("0"),
        )
        total_credit = sum(
            (self._cell_money(r, _COL_CREDIT) for r in range(self._table.rowCount())),
            Decimal("0"),
        )
        diff = total_debit - total_credit
        balanced = diff == 0 and total_debit > 0
        color = self._tokens.good if balanced else self._tokens.bad
        self._balance_label.setText(
            f"Tổng Nợ: {format_money(total_debit)}    "
            f"Tổng Có: {format_money(total_credit)}    "
            f"Lệch: {format_money(diff)}"
        )
        self._balance_label.setStyleSheet(f"color: {color}; font-weight: 600;")

    # ----- data in/out --------------------------------------------------

    def _populate(self, entry: JournalEntry) -> None:
        self._ref.setText(entry.ref)
        self._date.setDate(QDate(entry.entry_date.year, entry.entry_date.month, entry.entry_date.day))
        self._description.setText(entry.description)
        for line in entry.lines:
            self._add_row(line)

    def _qdate_to_date(self) -> date:
        qd = self._date.date()
        return date(qd.year(), qd.month(), qd.day())

    def _submit(self, status: EntryStatus) -> None:
        self._status = status
        self.accept()

    def entry(self) -> JournalEntry:
        entry = self._original or JournalEntry(ref="")
        entry.ref = self._ref.text().strip()
        entry.entry_date = self._qdate_to_date()
        entry.description = self._description.text().strip()
        entry.status = self._status
        entry.lines = []
        for row in range(self._table.rowCount()):
            code = self._cell_text(row, _COL_CODE)
            debit = self._cell_money(row, _COL_DEBIT)
            credit = self._cell_money(row, _COL_CREDIT)
            if not code and debit == 0 and credit == 0:
                continue  # skip fully-empty rows
            entry.lines.append(
                JournalLine(
                    account_code=code,
                    account_name=self._account_names.get(code, ""),
                    description=self._cell_text(row, _COL_DESC),
                    debit=debit,
                    credit=credit,
                )
            )
        return entry
