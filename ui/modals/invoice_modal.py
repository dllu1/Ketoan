"""InvoiceEditModal: lập / sửa hóa đơn bán hàng / mua hàng (chứng từ + dòng hàng).

Định khoản Nợ/Có nằm *ngay trong bảng dòng hàng* (mỗi cột một tài khoản): một
hóa đơn có thể gồm nhiều mặt hàng, mỗi mặt hàng vào một phân vùng kho (TK kho)
và một cặp định khoản TK Nợ / TK Có khác nhau.

Hóa đơn **mua hàng** có thêm bảng thứ hai — *chi phí dịch vụ mua ngoài* (giao
hàng, tiền điện, tiền nước…). Những dòng này không có số lượng / đơn giá, chỉ có
thành tiền, không chạy nhập kho, và mang thêm ô "Phân bổ vào" = tài khoản sẽ
nhận chi phí khi kết chuyển giá thành sau này.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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
    InvoiceLineType,
    InvoiceStatus,
    PaymentMethod,
)
from domain.models.item import Item
from domain.models.partner import PartnerType
from domain.money import format_money, parse_money
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.collapsible import CollapsibleSection
from ui.primitives.date_edit import DateEdit
from ui.primitives.enter_nav import (
    EnterNavDelegate,
    install_form_enter_nav,
    install_grid_enter_nav,
)

(_COL_CODE, _COL_NAME, _COL_UNIT, _COL_WAREHOUSE, _COL_DEBIT, _COL_CREDIT,
 _COL_QTY, _COL_PRICE, _COL_VAT, _COL_AMOUNT) = range(10)

# Bảng chi phí dịch vụ mua ngoài (chỉ hóa đơn mua hàng).
(_CC_NAME, _CC_DEBIT, _CC_CREDIT, _CC_TARGET, _CC_VAT, _CC_AMOUNT) = range(6)

# Dòng chi phí mới: Nợ 154 (chi phí SXKD dở dang), phân bổ về 155 (giá thành
# thành phẩm) — hai ô này người dùng đổi thoải mái ngay trên lưới.
_DEFAULT_COST_ACCOUNT = "154"
_DEFAULT_COST_TARGET = "155"

# Gợi ý cho ô "Phân bổ vào": nơi chi phí mua ngoài thường được kết chuyển tới.
_ALLOCATION_HINTS = {
    "155": "155 — Giá thành thành phẩm",
    "154": "154 — Chi phí SXKD dở dang",
    "156": "156 — Hàng hóa",
    "632": "632 — Giá vốn hàng bán",
    "641": "641 — Chi phí bán hàng",
    "642": "642 — Chi phí quản lý doanh nghiệp",
    "242": "242 — Chi phí trả trước (phân bổ dần)",
}

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


class _CompleterDelegate(EnterNavDelegate):
    def __init__(self, completer: QCompleter, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._completer = completer

    def createEditor(self, parent, option, index):  # noqa: N802 (Qt signature)
        editor = QLineEdit(parent)
        editor.setCompleter(self._completer)
        return editor


class _AccountCompleterDelegate(EnterNavDelegate):
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
        # DateEdit: bôi đen + Delete để xóa trắng rồi gõ tay cả ngày/tháng/năm.
        self._date = DateEdit()
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

        items_title = (
            "NGUYÊN VẬT LIỆU · HÀNG HÓA" if self._kind is InvoiceKind.PURCHASE
            else "DÒNG HÀNG · ĐỊNH KHOẢN"
        )

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
        # Enter = sang ô sửa được kế tiếp; hết bảng thì tự mở dòng mới.
        install_grid_enter_nav(self._table, add_row=self._add_row)

        line_buttons = QHBoxLayout()
        btn_add = Button("+ Thêm dòng", icon_name="plus")
        btn_add.clicked.connect(lambda: self._add_row())
        btn_del = Button("− Xóa dòng", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_del.clicked.connect(self._remove_current_row)
        line_buttons.addWidget(btn_add)
        line_buttons.addWidget(btn_del)
        line_buttons.addStretch(1)

        # Bảng hàng hóa gói trong khối thu gọn được (dạng drop down; mặc định mở).
        self._items_section = CollapsibleSection(items_title, expanded=True)
        self._items_section.add_widget(self._table, 1)
        self._items_section.add_layout(line_buttons)

        # ----- chi phí dịch vụ mua ngoài (chỉ hóa đơn mua hàng) -----------
        self._cost_section = self._build_cost_section(account_entries)

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
        layout.addWidget(self._items_section, 1)
        layout.addWidget(self._cost_section)
        layout.addWidget(self._totals_label)
        layout.addLayout(footer)

        # Enter ở ô nhập của chứng từ = sang ô sau (không bấm "Ghi sổ" nhầm).
        install_form_enter_nav(self)

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

    # ----- bảng chi phí dịch vụ mua ngoài -------------------------------

    def _build_cost_section(
        self, account_entries: list[tuple[str, str]]
    ) -> QWidget:
        """Bảng "chi phí dịch vụ khác" — chỉ dựng thật cho hóa đơn mua hàng.

        Bán hàng vẫn được trả về một widget rỗng đã ẩn, để phần bố cục và các
        vòng lặp phía dưới không phải rẽ nhánh theo loại chứng từ.
        """
        self._cost_table = QTableWidget(0, 6)
        if self._kind is not InvoiceKind.PURCHASE:
            section = QWidget()
            section.hide()
            return section

        # Khối chi phí dịch vụ thu gọn được — mặc định đóng vì thường bỏ trống.
        section = CollapsibleSection(
            "CHI PHÍ DỊCH VỤ KHÁC · CHỜ PHÂN BỔ", expanded=False
        )
        hint = QLabel(
            "Giao hàng, tiền điện, tiền nước… — không có số lượng / đơn giá. "
            "“Phân bổ vào” là tài khoản sẽ nhận chi phí khi kết chuyển giá thành."
        )
        hint.setObjectName("DialogSubtitle")
        hint.setWordWrap(True)

        self._cost_table.setHorizontalHeaderLabels(
            ["Nội dung chi phí", "TK Nợ", "TK Có", "Phân bổ vào", "VAT %", "Thành tiền"]
        )
        # "Phân bổ vào" gợi ý các TK kết chuyển quen thuộc trước, rồi tới toàn bộ
        # hệ thống tài khoản — người dùng vẫn tự do chọn TK bất kỳ.
        hinted = [(code, label_) for code, label_ in _ALLOCATION_HINTS.items()]
        hinted_codes = set(_ALLOCATION_HINTS)
        target_entries = hinted + [
            (code, text) for code, text in account_entries if code not in hinted_codes
        ]
        for col, entries in (
            (_CC_DEBIT, account_entries),
            (_CC_CREDIT, account_entries),
            (_CC_TARGET, target_entries),
        ):
            self._cost_table.setItemDelegateForColumn(
                col, _AccountCompleterDelegate(entries, self)
            )
        self._cost_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._cost_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._cost_table.setAlternatingRowColors(True)
        self._cost_table.setShowGrid(False)
        self._cost_table.verticalHeader().setDefaultSectionSize(34)
        self._cost_table.setMaximumHeight(160)
        cost_head = self._cost_table.horizontalHeader()
        cost_head.setSectionResizeMode(_CC_NAME, QHeaderView.Stretch)
        for col in (_CC_DEBIT, _CC_CREDIT, _CC_TARGET, _CC_VAT, _CC_AMOUNT):
            cost_head.setSectionResizeMode(col, QHeaderView.Fixed)
        self._cost_table.setColumnWidth(_CC_DEBIT, 80)
        self._cost_table.setColumnWidth(_CC_CREDIT, 80)
        self._cost_table.setColumnWidth(_CC_TARGET, 100)
        self._cost_table.setColumnWidth(_CC_VAT, 60)
        self._cost_table.setColumnWidth(_CC_AMOUNT, 126)
        self._cost_table.itemChanged.connect(lambda _: self._recompute_totals())
        install_grid_enter_nav(self._cost_table, add_row=self._add_cost_row)

        cost_buttons = QHBoxLayout()
        btn_add_cost = Button("+ Thêm chi phí", icon_name="plus")
        btn_add_cost.clicked.connect(lambda: self._add_cost_row())
        btn_del_cost = Button("− Xóa chi phí", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_del_cost.clicked.connect(self._remove_current_cost_row)
        cost_buttons.addWidget(btn_add_cost)
        cost_buttons.addWidget(btn_del_cost)
        cost_buttons.addStretch(1)

        section.add_widget(hint)
        section.add_widget(self._cost_table)
        section.add_layout(cost_buttons)
        return section

    def _add_cost_row(self, line: InvoiceLine | None = None) -> None:
        table = self._cost_table
        table.blockSignals(True)
        row = table.rowCount()
        table.insertRow(row)
        values = [
            line.item_name if line else "",
            (line.debit_account if line and line.debit_account else _DEFAULT_COST_ACCOUNT),
            (line.credit_account if line and line.credit_account
             else self._current_payment().payable_account),
            (line.allocation_target if line and line.allocation_target
             else _DEFAULT_COST_TARGET),
            f"{line.vat_rate:g}" if line else "10",
            format_money(line.amount) if line and line.amount else "",
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col in (_CC_VAT, _CC_AMOUNT):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(row, col, item)
        table.blockSignals(False)
        self._recompute_totals()

    def _remove_current_cost_row(self) -> None:
        row = self._cost_table.currentRow()
        if row >= 0:
            self._cost_table.removeRow(row)
            self._recompute_totals()

    def _cost_text(self, row: int, col: int) -> str:
        item = self._cost_table.item(row, col)
        return item.text().strip() if item else ""

    def _cost_money(self, row: int, col: int) -> Decimal:
        try:
            return parse_money(self._cost_text(row, col))
        except ValueError:
            return Decimal("0")

    def _has_cost_table(self) -> bool:
        return self._kind is InvoiceKind.PURCHASE

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
        if not self._has_cost_table():
            return
        # Dòng chi phí cũng trả cho NCC/tiền, nên TK Có đi theo hình thức thanh toán.
        self._cost_table.blockSignals(True)
        for row in range(self._cost_table.rowCount()):
            current = self._cost_text(row, _CC_CREDIT)
            if not current or current in _PURCHASE_CREDIT_PAYMENT:
                item = self._cost_table.item(row, _CC_CREDIT)
                if item is not None:
                    item.setText(pm.payable_account)
        self._cost_table.blockSignals(False)

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
        elif item.column() == _COL_WAREHOUSE:
            self._sync_debit_to_warehouse(item.row())
        self._refresh_amount(item.row())

    def _sync_debit_to_warehouse(self, row: int) -> None:
        """Mua hàng: gõ mã kho thì TK Nợ chạy theo (hàng ghi vào chính kho đó).

        Chỉ áp dụng cho hóa đơn mua; bán hàng thì TK Nợ là tiền/phải thu nên mã
        kho không liên quan.
        """
        if self._kind is not InvoiceKind.PURCHASE:
            return
        warehouse = self._cell_text(row, _COL_WAREHOUSE)
        if not warehouse:
            return
        self._table.blockSignals(True)
        self._set_cell(row, _COL_DEBIT, warehouse)
        self._table.blockSignals(False)

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
        cost_total = Decimal("0")
        if self._has_cost_table():
            for row in range(self._cost_table.rowCount()):
                amount = self._cost_money(row, _CC_AMOUNT)
                vat_rate = self._cost_money(row, _CC_VAT)
                cost_total += amount
                vat_total += (amount * vat_rate / Decimal("100")).quantize(Decimal("1"))
        grand = subtotal + cost_total + vat_total
        cost_part = (
            f"Chi phí DV {format_money(cost_total)}    " if cost_total else ""
        )
        self._totals_label.setText(
            f"Tiền hàng {format_money(subtotal)}    "
            f"{cost_part}"
            f"Thuế GTGT {format_money(vat_total)}    "
            f"TỔNG {format_money(grand)}"
        )
        self._update_section_summaries(cost_total)

    def _update_section_summaries(self, cost_total: Decimal) -> None:
        """Chữ tóm tắt cạnh tiêu đề mỗi khối thu gọn (đếm dòng / báo có chi phí)."""
        self._items_section.set_summary(f"· {self._table.rowCount()} dòng")
        if isinstance(self._cost_section, CollapsibleSection):
            n = self._cost_table.rowCount()
            self._cost_section.set_summary(
                f"· {n} dòng · {format_money(cost_total)}" if n else ""
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
            if line.is_cost and self._has_cost_table():
                self._add_cost_row(line)
            else:
                self._add_row(line)
        # Chứng từ có sẵn dòng chi phí → mở khối chi phí để thấy ngay, khỏi tưởng mất.
        if isinstance(self._cost_section, CollapsibleSection) \
                and self._cost_table.rowCount() > 0:
            self._cost_section.set_expanded(True)

    def _qdate_to_date(self) -> date:
        # DateEdit tự diễn giải chuỗi nếu người dùng đang gõ tay dở.
        return self._date.date_value()

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
        invoice.lines.extend(self._cost_lines())
        return invoice

    def _cost_lines(self) -> list[InvoiceLine]:
        """Dòng chi phí dịch vụ → InvoiceLine loại COST.

        Chi phí không có số lượng thật; lưu ``quantity = 1`` và ``unit_price =``
        thành tiền để mọi công thức tiền/thuế dùng chung với dòng hàng.
        """
        if not self._has_cost_table():
            return []
        lines: list[InvoiceLine] = []
        for row in range(self._cost_table.rowCount()):
            name = self._cost_text(row, _CC_NAME)
            amount = self._cost_money(row, _CC_AMOUNT)
            if not name and amount == 0:
                continue
            lines.append(
                InvoiceLine(
                    item_code="",
                    item_name=name,
                    unit="",
                    quantity=Decimal("1"),
                    unit_price=amount,
                    vat_rate=self._cost_money(row, _CC_VAT),
                    account_code="",
                    debit_account=self._cost_text(row, _CC_DEBIT),
                    credit_account=self._cost_text(row, _CC_CREDIT),
                    line_type=InvoiceLineType.COST,
                    allocation_target=self._cost_text(row, _CC_TARGET),
                )
            )
        return lines
