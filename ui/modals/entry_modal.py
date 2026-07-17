"""EntryModal: create / edit a balanced journal entry (bút toán Nợ/Có)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QFormLayout,
    QFrame,
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
from data.repositories.item_repo import ItemRepository
from domain.models.invoice import Invoice, InvoiceKind, InvoiceLine, InvoiceStatus
from domain.models.journal import EntryStatus, JournalEntry, JournalLine
from domain.money import format_money, parse_money
from ui.primitives.button import Button, ButtonVariant

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
        self.setMinimumSize(760, 640)
        self.setWindowTitle("Bút toán mới" if entry is None else f"Sửa: {entry.ref}")

        self._original = entry
        self._status = EntryStatus.POSTED

        accounts = AccountRepository().list_all()
        self._account_names = {a.code: a.name for a in accounts}
        completer = QCompleter([a.code for a in accounts], self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)

        self._items = {i.code: i for i in ItemRepository().list_all()}

        # ----- header ----------------------------------------------------
        header_frame = QFrame()
        header_frame.setObjectName("DialogHeader")
        hf = QVBoxLayout(header_frame)
        hf.setContentsMargins(0, 0, 0, 12)
        hf.setSpacing(2)
        title = QLabel("Bút toán mới" if entry is None else f"Sửa bút toán · {entry.ref}")
        title.setObjectName("DialogTitle")
        subtitle = QLabel("Định khoản Nợ / Có · Ctrl+S lưu · Esc đóng")
        subtitle.setObjectName("DialogSubtitle")
        hf.addWidget(title)
        hf.addWidget(subtitle)

        # ----- metadata --------------------------------------------------
        self._ref = QLineEdit()
        self._ref.setPlaceholderText("VD: PKT-0034")
        self._date = QDateEdit()
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("dd/MM/yyyy")
        self._date.setDate(QDate.currentDate())
        self._description = QLineEdit()
        self._description.setPlaceholderText("Diễn giải chung của bút toán…")

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.addRow("Số CT *", self._ref)
        form.addRow("Ngày", self._date)
        form.addRow("Diễn giải", self._description)

        # ----- optional invoice + goods (auto-routed to Bán hàng / Mua hàng) --
        # Two compact columns so the optional block doesn't crowd the dialog.
        optional_label = QLabel("CHỨNG TỪ KÈM THEO (tùy chọn) · nhập Số hóa đơn để tự đẩy sang Bán/Mua hàng")
        optional_label.setObjectName("SectionLabel")

        self._invoice_no = QLineEdit()
        self._invoice_no.setPlaceholderText("Để trống nếu không kèm")
        self._invoice_kind = QComboBox()
        self._invoice_kind.addItem("Bán hàng (đầu ra)", InvoiceKind.SALE)
        self._invoice_kind.addItem("Mua hàng (đầu vào)", InvoiceKind.PURCHASE)
        self._invoice_kind.setEnabled(False)
        self._invoice_no.textChanged.connect(
            lambda text: self._invoice_kind.setEnabled(bool(text.strip()))
        )

        invoice_form = QFormLayout()
        invoice_form.setHorizontalSpacing(12)
        invoice_form.setVerticalSpacing(8)
        invoice_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        invoice_form.addRow("Số hóa đơn", self._invoice_no)
        invoice_form.addRow("Loại", self._invoice_kind)

        self._item_code = QLineEdit()
        self._item_code.setPlaceholderText("VD: HH001")
        item_completer = QCompleter(list(self._items), self)
        item_completer.setCaseSensitivity(Qt.CaseInsensitive)
        item_completer.setFilterMode(Qt.MatchContains)
        self._item_code.setCompleter(item_completer)
        self._item_code.editingFinished.connect(self._autofill_item)
        self._item_name = QLineEdit()
        self._item_name.setPlaceholderText("Tên hàng hóa…")
        self._item_qty = QLineEdit()
        self._item_qty.setPlaceholderText("0")
        self._item_qty.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._item_price = QLineEdit()
        self._item_price.setPlaceholderText("0")
        self._item_price.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        goods_form = QFormLayout()
        goods_form.setHorizontalSpacing(12)
        goods_form.setVerticalSpacing(8)
        goods_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        goods_form.addRow("Mã vật tư", self._item_code)
        goods_form.addRow("Tên hàng", self._item_name)
        goods_form.addRow("Số lượng", self._item_qty)
        goods_form.addRow("Đơn giá", self._item_price)

        optional_row = QHBoxLayout()
        optional_row.setSpacing(24)
        optional_row.addLayout(invoice_form, 1)
        optional_row.addLayout(goods_form, 1)

        grid_label = QLabel("DÒNG BÚT TOÁN (NỢ / CÓ)")
        grid_label.setObjectName("SectionLabel")

        # ----- lines grid ------------------------------------------------
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["TK", "Diễn giải", "Nợ", "Có"])
        self._table.setItemDelegateForColumn(_COL_CODE, _AccountDelegate(completer, self))
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setCornerButtonEnabled(False)
        self._table.setMinimumHeight(180)
        self._table.verticalHeader().setDefaultSectionSize(34)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(_COL_CODE, QHeaderView.Fixed)
        header.setSectionResizeMode(_COL_DESC, QHeaderView.Stretch)
        header.setSectionResizeMode(_COL_DEBIT, QHeaderView.Fixed)
        header.setSectionResizeMode(_COL_CREDIT, QHeaderView.Fixed)
        self._table.setColumnWidth(_COL_CODE, 110)
        self._table.setColumnWidth(_COL_DEBIT, 150)
        self._table.setColumnWidth(_COL_CREDIT, 150)
        for col in (_COL_DEBIT, _COL_CREDIT):
            header_item = self._table.horizontalHeaderItem(col)
            header_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
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
        footer.setSpacing(8)
        btn_cancel = Button("Hủy", variant=ButtonVariant.GHOST)
        btn_cancel.clicked.connect(self.reject)
        btn_draft = Button("Lưu nháp", icon_name="edit")
        btn_draft.clicked.connect(lambda: self._submit(EntryStatus.DRAFT))
        self._btn_post = Button("Ghi sổ", variant=ButtonVariant.PRIMARY, icon_name="check")
        self._btn_post.clicked.connect(lambda: self._submit(EntryStatus.POSTED))
        footer.addStretch(1)
        footer.addWidget(btn_cancel)
        footer.addWidget(btn_draft)
        footer.addWidget(self._btn_post)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        layout.addWidget(header_frame)
        layout.addLayout(form)
        layout.addWidget(optional_label)
        layout.addLayout(optional_row)
        layout.addWidget(grid_label)
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
        flag = "✓ CÂN ĐỐI" if balanced else "✗ CHƯA CÂN"
        self._balance_label.setText(
            f"{flag}        "
            f"Tổng Nợ {format_money(total_debit)}   =   Tổng Có {format_money(total_credit)}"
            f"        Lệch {format_money(diff)}"
        )
        self._balance_label.setProperty("balanced", "true" if balanced else "false")
        self._balance_label.style().unpolish(self._balance_label)
        self._balance_label.style().polish(self._balance_label)
        self._btn_post.setEnabled(balanced)

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

    def _autofill_item(self) -> None:
        """Fill name / price from the directory when a known mã vật tư is typed."""
        product = self._items.get(self._item_code.text().strip())
        if product is None:
            return
        if not self._item_name.text().strip():
            self._item_name.setText(product.name)
        if not self._item_price.text().strip():
            self._item_price.setText(format_money(product.unit_price))

    def _parse_amount(self, line_edit: QLineEdit) -> Decimal:
        try:
            return parse_money(line_edit.text())
        except ValueError:
            return Decimal("0")

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

    def invoice_request(self) -> tuple[Invoice, InvoiceKind] | None:
        """Optional invoice to route into the Bán hàng / Mua hàng tab.

        Returns ``None`` unless the user filled in a số hóa đơn — that field is
        the trigger. The invoice is built as a DRAFT (no posting) so it appears
        in the matching tab as a document without double-counting the journal
        entry the user already typed here; they can ghi sổ it from that tab.
        """
        invoice_no = self._invoice_no.text().strip()
        if not invoice_no:
            return None
        # Coerce: Qt returns str-based enum userData as a plain str, which would
        # make `kind is InvoiceKind.SALE` (in journal_screen) always false.
        kind = InvoiceKind(self._invoice_kind.currentData())
        product = self._items.get(self._item_code.text().strip())
        line = InvoiceLine(
            item_code=self._item_code.text().strip(),
            item_name=self._item_name.text().strip() or (product.name if product else ""),
            unit=product.unit if product else "",
            quantity=self._parse_amount(self._item_qty),
            unit_price=self._parse_amount(self._item_price),
            vat_rate=product.vat_rate if product else Decimal("10"),
            account_code=product.account_code if product else "",
        )
        invoice = Invoice(
            ref=invoice_no,
            invoice_no=invoice_no,
            invoice_date=self._qdate_to_date(),
            kind=kind,
            status=InvoiceStatus.DRAFT,
            description=self._description.text().strip(),
            lines=[line],
        )
        return invoice, kind
