"""InvoiceEditModal: lập / sửa hóa đơn bán hàng / mua hàng (chứng từ + dòng hàng).

Định khoản Nợ/Có nằm *ngay trong bảng dòng hàng* (mỗi cột một tài khoản): một
hóa đơn có thể gồm nhiều mặt hàng, mỗi mặt hàng vào một phân vùng kho (TK kho)
và một cặp định khoản TK Nợ / TK Có khác nhau.
"""
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
from data.repositories.partner_repo import PartnerRepository
from domain.models.invoice import (
    Invoice,
    InvoiceKind,
    InvoiceLine,
    InvoiceStatus,
    PaymentMethod,
)
from domain.models.item import Item
from domain.models.partner import PartnerType
from domain.money import format_money, parse_money
from ui.primitives.button import Button, ButtonVariant

(_COL_CODE, _COL_NAME, _COL_UNIT, _COL_WAREHOUSE, _COL_DEBIT, _COL_CREDIT,
 _COL_QTY, _COL_PRICE, _COL_VAT, _COL_AMOUNT) = range(10)

_PAYMENT_LABELS = {
    PaymentMethod.CREDIT: "Công nợ",
    PaymentMethod.CASH: "Tiền mặt (111)",
    PaymentMethod.BANK: "Chuyển khoản (112)",
}

# Doanh thu mặc định cho hóa đơn bán hàng (khớp SalesService._REVENUE_ACCOUNT).
_REVENUE_ACCOUNT = "511"

# Các tài khoản tiền/công nợ do hình thức thanh toán điều khiển. Khi đổi hình
# thức thanh toán, chỉ những ô đang giữ một trong các TK này (hoặc bỏ trống) mới
# được cập nhật — định khoản người dùng tự gõ (vd 5111) được giữ nguyên.
_SALE_DEBIT_PAYMENT = {"111", "112", "131"}
_PURCHASE_CREDIT_PAYMENT = {"111", "112", "331"}

# "Kho" trong hệ thống = tài khoản kho TT200. Mã kho chọn trên mỗi dòng hàng
# vừa định tuyến bút toán Nợ/Có kho, vừa cập nhật Nhập–Xuất–Tồn.
_STOCK_ACCOUNTS = ("152", "153", "155", "156")
_STOCK_ACCOUNT_LABELS = {
    "152": "152 — Nguyên vật liệu",
    "153": "153 — Công cụ, dụng cụ",
    "155": "155 — Thành phẩm",
    "156": "156 — Hàng hóa",
}

# Per-kind copy: (window/title noun, document title, subtitle, partner noun, partner abbr, partner type filter)
_KIND_COPY = {
    InvoiceKind.SALE: (
        "Hóa đơn", "Hóa đơn bán hàng", "Nhập chứng từ khách hàng",
        "Khách hàng", "KH", PartnerType.CUSTOMER,
    ),
    InvoiceKind.PURCHASE: (
        "Hóa đơn mua", "Hóa đơn mua hàng", "Nhập chứng từ nhà cung cấp",
        "Nhà cung cấp", "NCC", PartnerType.SUPPLIER,
    ),
}


class _CompleterDelegate(QStyledItemDelegate):
    def __init__(self, completer: QCompleter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._completer = completer

    def createEditor(self, parent, option, index):  # noqa: N802 (Qt signature)
        editor = QLineEdit(parent)
        editor.setCompleter(self._completer)
        return editor


class _AccountCompleterDelegate(QStyledItemDelegate):
    """Ô nhập tài khoản: QLineEdit + gợi ý ``"mã — tên"``; ô chỉ lưu mã trần.

    Dùng cho TK kho / TK Nợ / TK Có. Popup gợi ý hiện kèm *tên* tài khoản và lọc
    theo cả mã lẫn tên (không phân biệt hoa thường) để dễ tìm; khi chọn/gõ xong,
    ô lưu mã trần (vd ``"131"``) và gắn tooltip = nhãn đầy đủ để hover thấy tên.

    Thay cho QComboBox lồng trong ô hẹp (gây lỗi nhập liệu / mất phím khi gõ).
    """

    def __init__(
        self, entries: list[tuple[str, str]], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        # entries: (mã, "mã — tên"). Giữ cả hai chiều để map nhãn↔mã khi commit.
        self._labels = [label for _, label in entries]
        self._code_by_label = {label: code for code, label in entries}
        self._label_by_code = {code: label for code, label in entries}

    def createEditor(self, parent, option, index):  # noqa: N802 (Qt signature)
        editor = QLineEdit(parent)
        completer = QCompleter(self._labels, editor)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        editor.setCompleter(completer)
        return editor

    def setEditorData(self, editor: QLineEdit, index):  # noqa: N802
        editor.setText((index.data(Qt.EditRole) or "").strip())

    def setModelData(self, editor: QLineEdit, model, index):  # noqa: N802
        text = editor.text().strip()
        # Chọn từ popup → text là nhãn đầy đủ; gõ tay → tách lấy token mã đầu.
        code = self._code_by_label.get(text)
        if code is None:
            code = text.split(" — ")[0].split()[0] if text else ""
        model.setData(index, code, Qt.EditRole)
        model.setData(index, self._label_by_code.get(code, code), Qt.ToolTipRole)


class InvoiceModal(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        invoice: Invoice | None = None,
        kind: InvoiceKind = InvoiceKind.SALE,
    ) -> None:
        super().__init__(parent)
        self._kind = invoice.kind if invoice is not None else kind
        noun, doc_title, doc_subtitle, partner_noun, partner_abbr, partner_type = _KIND_COPY[self._kind]

        self.setObjectName("InvoiceModal")
        self.setModal(True)
        self.setMinimumSize(1040, 660)
        self.setWindowTitle(f"{noun} mới" if invoice is None else f"Sửa: {invoice.ref}")

        self._original = invoice
        self._status = InvoiceStatus.POSTED
        # Quyết định lưu đối tác lạ qua báo đỏ trong modal: None = chưa trả lời
        # (màn danh sách sẽ hỏi tiếp), True = người dùng bấm "Lưu vào danh mục".
        self._save_partner: bool | None = None
        self._partner_noun = partner_noun

        self._items = {i.code: i for i in ItemRepository().list_all()}
        self._partners = {p.code: p for p in PartnerRepository().list_all(partner_type)}
        self._accounts = AccountRepository().list_all()

        item_completer = QCompleter(list(self._items), self)
        item_completer.setCaseSensitivity(Qt.CaseInsensitive)
        item_completer.setFilterMode(Qt.MatchContains)

        # ----- header ----------------------------------------------------
        header = QFrame()
        header.setObjectName("DialogHeader")
        hf = QVBoxLayout(header)
        hf.setContentsMargins(0, 0, 0, 12)
        hf.setSpacing(2)
        title = QLabel(doc_title if invoice is None else f"Sửa · {invoice.ref}")
        title.setObjectName("DialogTitle")
        subtitle = QLabel(f"{doc_subtitle} · Ctrl+S ghi sổ · Esc đóng")
        subtitle.setObjectName("DialogSubtitle")
        hf.addWidget(title)
        hf.addWidget(subtitle)

        # ----- document metadata -----------------------------------------
        self._ref = QLineEdit()
        self._ref.setPlaceholderText("VD: HD-0001")
        self._invoice_no = QLineEdit()
        self._invoice_no.setPlaceholderText("Số hóa đơn GTGT")
        self._serial = QLineEdit()
        self._serial.setPlaceholderText("Ký hiệu / mẫu số")
        self._date = QDateEdit()
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("dd/MM/yyyy")
        self._date.setDate(QDate.currentDate())
        self._payment = QComboBox()
        for pm in PaymentMethod:
            self._payment.addItem(_PAYMENT_LABELS[pm], pm)
        self._description = QLineEdit()
        self._description.setPlaceholderText("Diễn giải chung…")

        doc_form = QFormLayout()
        doc_form.setHorizontalSpacing(14)
        doc_form.setVerticalSpacing(8)
        doc_form.addRow("Số CT *", self._ref)
        doc_form.addRow("Số HĐ", self._invoice_no)
        doc_form.addRow("Ký hiệu", self._serial)
        doc_form.addRow("Ngày", self._date)
        doc_form.addRow("Thanh toán", self._payment)
        doc_form.addRow("Diễn giải", self._description)

        # ----- partner (denormalized; guest-friendly) --------------------
        self._partner_code = QLineEdit()
        self._partner_code.setPlaceholderText(
            "Để trống = khách lẻ" if self._kind is InvoiceKind.SALE else "Để trống = NCC vãng lai"
        )
        partner_completer = QCompleter(list(self._partners), self)
        partner_completer.setCaseSensitivity(Qt.CaseInsensitive)
        partner_completer.setFilterMode(Qt.MatchContains)
        self._partner_code.setCompleter(partner_completer)
        self._partner_code.editingFinished.connect(self._fill_partner)
        self._partner_name = QLineEdit()
        self._partner_tax = QLineEdit()
        self._partner_address = QLineEdit()

        cust_form = QFormLayout()
        cust_form.setHorizontalSpacing(14)
        cust_form.setVerticalSpacing(8)
        cust_form.addRow(f"Mã {partner_abbr}", self._partner_code)
        cust_form.addRow(f"Tên {partner_abbr}", self._partner_name)
        cust_form.addRow("MST", self._partner_tax)
        cust_form.addRow("Địa chỉ", self._partner_address)

        meta = QHBoxLayout()
        meta.setSpacing(24)
        meta.addLayout(doc_form, 1)
        meta.addLayout(cust_form, 1)

        grid_label = QLabel("DÒNG HÀNG · ĐỊNH KHOẢN")
        grid_label.setObjectName("SectionLabel")

        # ----- lines grid (mỗi dòng: mặt hàng + TK kho + định khoản Nợ/Có) -
        self._table = QTableWidget(0, 10)
        self._table.setHorizontalHeaderLabels(
            ["Mã hàng", "Tên hàng", "ĐVT", "Mã kho", "TK Nợ", "TK Có",
             "SL", "Đơn giá", "VAT %", "Thành tiền"]
        )
        # Gợi ý tài khoản kèm tên: TK kho giới hạn 4 kho TT200; TK Nợ/Có là toàn
        # bộ hệ thống tài khoản. Cả ba lọc theo mã hoặc tên khi gõ.
        stock_entries = [(code, _STOCK_ACCOUNT_LABELS[code]) for code in _STOCK_ACCOUNTS]
        account_entries = [(acc.code, acc.display_label) for acc in self._accounts]
        self._table.setItemDelegateForColumn(_COL_CODE, _CompleterDelegate(item_completer, self))
        self._table.setItemDelegateForColumn(_COL_WAREHOUSE, _AccountCompleterDelegate(stock_entries, self))
        self._table.setItemDelegateForColumn(_COL_DEBIT, _AccountCompleterDelegate(account_entries, self))
        self._table.setItemDelegateForColumn(_COL_CREDIT, _AccountCompleterDelegate(account_entries, self))
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setDefaultSectionSize(34)
        head = self._table.horizontalHeader()
        head.setSectionResizeMode(_COL_NAME, QHeaderView.Stretch)
        for col in (_COL_CODE, _COL_UNIT, _COL_WAREHOUSE, _COL_DEBIT, _COL_CREDIT,
                    _COL_QTY, _COL_PRICE, _COL_VAT, _COL_AMOUNT):
            head.setSectionResizeMode(col, QHeaderView.Fixed)
        self._table.setColumnWidth(_COL_CODE, 104)
        self._table.setColumnWidth(_COL_UNIT, 52)
        self._table.setColumnWidth(_COL_WAREHOUSE, 80)
        self._table.setColumnWidth(_COL_DEBIT, 80)
        self._table.setColumnWidth(_COL_CREDIT, 80)
        self._table.setColumnWidth(_COL_QTY, 66)
        self._table.setColumnWidth(_COL_PRICE, 116)
        self._table.setColumnWidth(_COL_VAT, 60)
        self._table.setColumnWidth(_COL_AMOUNT, 126)
        self._table.itemChanged.connect(self._on_cell_changed)

        line_buttons = QHBoxLayout()
        btn_add = Button("+ Thêm dòng", icon_name="plus")
        btn_add.clicked.connect(lambda: self._add_row())
        btn_del = Button("− Xóa dòng", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_del.clicked.connect(self._remove_current_row)
        line_buttons.addWidget(btn_add)
        line_buttons.addWidget(btn_del)
        line_buttons.addStretch(1)

        self._totals_label = QLabel()
        self._totals_label.setObjectName("BalanceBar")
        self._totals_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # ----- footer ----------------------------------------------------
        footer = QHBoxLayout()
        footer.setSpacing(8)
        btn_cancel = Button("Hủy", variant=ButtonVariant.GHOST)
        btn_cancel.clicked.connect(self.reject)
        btn_draft = Button("Lưu nháp", icon_name="edit")
        btn_draft.clicked.connect(lambda: self._submit(InvoiceStatus.DRAFT))
        btn_post = Button("Ghi sổ", variant=ButtonVariant.PRIMARY, icon_name="check")
        btn_post.clicked.connect(lambda: self._submit(InvoiceStatus.POSTED))
        footer.addStretch(1)
        footer.addWidget(btn_cancel)
        footer.addWidget(btn_draft)
        footer.addWidget(btn_post)

        # ----- báo đỏ: đối tác chưa có trong danh mục (ẩn mặc định) ------
        self._partner_alert = QFrame()
        self._partner_alert.setObjectName("PartnerAlertBanner")
        self._partner_alert.setStyleSheet(
            "#PartnerAlertBanner {"
            " background: #fdecea; border: 1px solid #e74c3c; border-radius: 6px; }"
            "#PartnerAlertBanner QLabel { color: #c0392b; background: transparent;"
            " border: none; }"
        )
        alert_row = QHBoxLayout(self._partner_alert)
        alert_row.setContentsMargins(12, 8, 12, 8)
        alert_row.setSpacing(10)
        self._alert_label = QLabel("")
        alert_row.addWidget(self._alert_label, 1)
        self._btn_save_partner = Button(
            "Lưu vào danh mục", variant=ButtonVariant.DANGER, icon_name="check")
        self._btn_save_partner.clicked.connect(self._on_save_partner_clicked)
        alert_row.addWidget(self._btn_save_partner)
        self._partner_alert.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addWidget(header)
        layout.addWidget(self._partner_alert)
        layout.addLayout(meta)
        layout.addWidget(grid_label)
        layout.addWidget(self._table, 1)
        layout.addLayout(line_buttons)
        layout.addWidget(self._totals_label)
        layout.addLayout(footer)

        # New documents default to "Công nợ" (matches the Invoice model default);
        # an existing one gets its real method back in _populate.
        if invoice is None:
            self._payment.setCurrentIndex(self._payment.findData(PaymentMethod.CREDIT))

        # Đổi hình thức thanh toán → cập nhật cột định khoản do thanh toán điều khiển.
        self._payment.currentIndexChanged.connect(self._on_payment_changed)

        if invoice is not None:
            self._populate(invoice)
            self._ref.setReadOnly(True)
            self._maybe_show_partner_alert(invoice)
        else:
            self._add_row()
        self._recompute_totals()

    # ----- per-line account defaults ------------------------------------

    def _current_payment(self) -> PaymentMethod:
        # currentData() loses the enum type for str-based enums; coerce back.
        return PaymentMethod(self._payment.currentData())

    def _line_account_defaults(self) -> tuple[str, str]:
        """(TK Nợ, TK Có) mặc định cho một dòng mới theo loại CT + thanh toán."""
        pm = self._current_payment()
        if self._kind is InvoiceKind.PURCHASE:
            # Nợ kho (điền theo mặt hàng, mặc định 156) / Có phải trả/tiền.
            return "156", pm.payable_account
        # Bán hàng: Nợ tiền/phải thu / Có doanh thu (511).
        return pm.debit_account, _REVENUE_ACCOUNT

    def _on_payment_changed(self) -> None:
        """Cập nhật cột định khoản do thanh toán điều khiển trên mọi dòng.

        Chỉ thay những ô đang giữ một TK tiền/công nợ chuẩn (hoặc bỏ trống); định
        khoản người dùng tự gõ được giữ nguyên.
        """
        pm = self._current_payment()
        self._table.blockSignals(True)
        for row in range(self._table.rowCount()):
            if self._kind is InvoiceKind.PURCHASE:
                current = self._cell_text(row, _COL_CREDIT)
                if not current or current in _PURCHASE_CREDIT_PAYMENT:
                    self._set_cell(row, _COL_CREDIT, pm.payable_account)
            else:
                current = self._cell_text(row, _COL_DEBIT)
                if not current or current in _SALE_DEBIT_PAYMENT:
                    self._set_cell(row, _COL_DEBIT, pm.debit_account)
        self._table.blockSignals(False)

    # ----- row helpers --------------------------------------------------

    def _add_row(self, line: InvoiceLine | None = None) -> None:
        self._table.blockSignals(True)
        row = self._table.rowCount()
        self._table.insertRow(row)
        default_debit, default_credit = self._line_account_defaults()
        values = [
            line.item_code if line else "",
            line.item_name if line else "",
            line.unit if line else "",
            line.account_code if line else "",
            (line.debit_account if line and line.debit_account else default_debit),
            (line.credit_account if line and line.credit_account else default_credit),
            f"{line.quantity:g}" if line and line.quantity else "",
            format_money(line.unit_price) if line and line.unit_price else "",
            f"{line.vat_rate:g}" if line else "10",
            "",
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col in (_COL_QTY, _COL_PRICE, _COL_VAT, _COL_AMOUNT):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if col == _COL_AMOUNT:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row, col, item)
        self._table.blockSignals(False)
        self._refresh_amount(row)

    def _remove_current_row(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)
            self._recompute_totals()

    def _on_cell_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == _COL_CODE:
            self._autofill_from_item(item.row())
        self._refresh_amount(item.row())

    def _autofill_from_item(self, row: int) -> None:
        code = self._cell_text(row, _COL_CODE)
        product = self._items.get(code)
        if product is None:
            return
        self._table.blockSignals(True)
        self._set_cell(row, _COL_NAME, product.name)
        self._set_cell(row, _COL_UNIT, product.unit)
        # Mã kho mặc định = TK kho của mặt hàng (chỉ điền khi còn trống).
        if not self._cell_text(row, _COL_WAREHOUSE):
            self._set_cell(row, _COL_WAREHOUSE, product.account_code)
        # Mua hàng: TK Nợ (nơi hàng ghi vào) đi theo TK kho của dòng.
        if self._kind is InvoiceKind.PURCHASE:
            warehouse = self._cell_text(row, _COL_WAREHOUSE)
            if warehouse:
                self._set_cell(row, _COL_DEBIT, warehouse)
        if not self._cell_text(row, _COL_PRICE):
            self._set_cell(row, _COL_PRICE, format_money(product.unit_price))
        self._set_cell(row, _COL_VAT, f"{product.vat_rate:g}")
        self._table.blockSignals(False)

    def _refresh_amount(self, row: int) -> None:
        amount = self._cell_money(row, _COL_QTY) * self._cell_money(row, _COL_PRICE)
        self._table.blockSignals(True)
        self._set_cell(row, _COL_AMOUNT, format_money(amount) if amount else "")
        self._table.blockSignals(False)
        self._recompute_totals()

    # ----- cell access --------------------------------------------------

    def _cell_text(self, row: int, col: int) -> str:
        item = self._table.item(row, col)
        return item.text().strip() if item else ""

    def _set_cell(self, row: int, col: int, value: str) -> None:
        item = self._table.item(row, col)
        if item is None:
            item = QTableWidgetItem(value)
            self._table.setItem(row, col, item)
        else:
            item.setText(value)

    def _cell_money(self, row: int, col: int) -> Decimal:
        try:
            return parse_money(self._cell_text(row, col))
        except ValueError:
            return Decimal("0")

    # ----- totals -------------------------------------------------------

    def _recompute_totals(self) -> None:
        subtotal = Decimal("0")
        vat_total = Decimal("0")
        for row in range(self._table.rowCount()):
            amount = self._cell_money(row, _COL_QTY) * self._cell_money(row, _COL_PRICE)
            vat_rate = self._cell_money(row, _COL_VAT)
            subtotal += amount
            vat_total += (amount * vat_rate / Decimal("100")).quantize(Decimal("1"))
        grand = subtotal + vat_total
        self._totals_label.setText(
            f"Tiền hàng {format_money(subtotal)}    "
            f"Thuế GTGT {format_money(vat_total)}    "
            f"TỔNG {format_money(grand)}"
        )

    # ----- data in/out --------------------------------------------------

    def _fill_partner(self) -> None:
        partner = self._partners.get(self._partner_code.text().strip())
        if partner is None:
            return
        self._partner_name.setText(partner.name)
        self._partner_tax.setText(partner.tax_code)
        self._partner_address.setText(partner.address)

    # ----- báo đỏ đối tác lạ --------------------------------------------

    def _maybe_show_partner_alert(self, invoice: Invoice) -> None:
        """Hiện báo đỏ nếu đối tác (không phải khách lẻ) chưa có trong danh mục."""
        code = invoice.partner_code.strip()
        if not code:
            return  # khách lẻ / NCC vãng lai — không cần báo
        repo = PartnerRepository()
        if repo.find_by_code(code) is not None:
            return
        if invoice.partner_tax_code.strip() and \
                repo.find_by_tax_code(invoice.partner_tax_code) is not None:
            return
        label = invoice.partner_name or code
        self._alert_label.setText(
            f"⚠ {self._partner_noun} “{label}” chưa có trong danh mục."
        )
        self._partner_alert.show()

    def _on_save_partner_clicked(self) -> None:
        self._save_partner = True
        self._alert_label.setText(
            f"✓ Sẽ lưu {self._partner_noun} vào danh mục khi bấm Lưu nháp / Ghi sổ."
        )
        self._btn_save_partner.setEnabled(False)

    def wants_save_partner(self) -> bool | None:
        """True nếu người dùng đã bấm lưu đối tác trong modal; None nếu chưa trả lời."""
        return self._save_partner

    def _populate(self, invoice: Invoice) -> None:
        self._ref.setText(invoice.ref)
        self._invoice_no.setText(invoice.invoice_no)
        self._serial.setText(invoice.serial)
        self._date.setDate(QDate(invoice.invoice_date.year, invoice.invoice_date.month, invoice.invoice_date.day))
        idx = self._payment.findData(invoice.payment_method)
        if idx >= 0:
            self._payment.setCurrentIndex(idx)
        self._description.setText(invoice.description)
        self._partner_code.setText(invoice.partner_code)
        self._partner_name.setText(invoice.partner_name)
        self._partner_tax.setText(invoice.partner_tax_code)
        self._partner_address.setText(invoice.partner_address)
        for line in invoice.lines:
            # Định khoản đã lưu trên dòng thắng; chứng từ cũ (trống dòng) rơi về
            # định khoản đầu chứng từ rồi tới mặc định.
            if not line.debit_account:
                line.debit_account = invoice.debit_account
            if not line.credit_account:
                line.credit_account = invoice.credit_account
            self._add_row(line)

    def _qdate_to_date(self) -> date:
        qd = self._date.date()
        return date(qd.year(), qd.month(), qd.day())

    def _submit(self, status: InvoiceStatus) -> None:
        self._status = status
        self.accept()

    def invoice(self) -> Invoice:
        invoice = self._original or Invoice(ref="")
        invoice.kind = self._kind
        invoice.ref = self._ref.text().strip()
        invoice.invoice_no = self._invoice_no.text().strip()
        invoice.serial = self._serial.text().strip()
        invoice.invoice_date = self._qdate_to_date()
        # currentData() loses the enum type for str-based enums (Qt stores the
        # str subclass as a plain QString), so coerce back to PaymentMethod.
        invoice.payment_method = PaymentMethod(self._payment.currentData())
        # Định khoản giờ ở từng dòng; không còn định khoản chung đầu chứng từ.
        invoice.debit_account = ""
        invoice.credit_account = ""
        invoice.status = self._status
        invoice.description = self._description.text().strip()
        invoice.partner_code = self._partner_code.text().strip()
        invoice.partner_name = self._partner_name.text().strip()
        invoice.partner_tax_code = self._partner_tax.text().strip()
        invoice.partner_address = self._partner_address.text().strip()
        invoice.lines = []
        for row in range(self._table.rowCount()):
            code = self._cell_text(row, _COL_CODE)
            qty = self._cell_money(row, _COL_QTY)
            if not code and qty == 0:
                continue
            product: Item | None = self._items.get(code)
            warehouse = self._cell_text(row, _COL_WAREHOUSE)
            invoice.lines.append(
                InvoiceLine(
                    item_code=code,
                    item_name=self._cell_text(row, _COL_NAME),
                    unit=self._cell_text(row, _COL_UNIT),
                    quantity=qty,
                    unit_price=self._cell_money(row, _COL_PRICE),
                    vat_rate=self._cell_money(row, _COL_VAT),
                    # Mã kho (TK kho) trên dòng thắng; rỗng → theo mặt hàng.
                    account_code=warehouse or (product.account_code if product else ""),
                    # Định khoản Nợ/Có riêng từng dòng.
                    debit_account=self._cell_text(row, _COL_DEBIT),
                    credit_account=self._cell_text(row, _COL_CREDIT),
                )
            )
        return invoice
