"""CashVoucherModal: lập phiếu thu / phiếu chi (định khoản 1 đối ứng)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from data.repositories.account_repo import AccountRepository
from data.repositories.partner_repo import PartnerRepository
from domain.models.cash import CASH_ACCOUNTS, CashKind
from domain.models.partner import PartnerType

_KIND_TITLES = {CashKind.RECEIPT: "Phiếu thu", CashKind.PAYMENT: "Phiếu chi"}

# Đối tượng & tài khoản đối ứng mặc định theo loại phiếu: phiếu thu gắn với
# khách hàng (TK 131), phiếu chi gắn với nhà cung cấp (TK 331).
_PARTNER_BY_KIND = {
    CashKind.RECEIPT: (PartnerType.CUSTOMER, "131", "Khách hàng"),
    CashKind.PAYMENT: (PartnerType.SUPPLIER, "331", "Nhà cung cấp"),
}


class CashVoucherModal(QDialog):
    def __init__(self, parent: QWidget | None = None, *, kind: CashKind = CashKind.RECEIPT) -> None:
        super().__init__(parent)
        self._kind = kind
        self.setObjectName("CashVoucherModal")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setWindowTitle(_KIND_TITLES[kind])

        accounts = AccountRepository().list_all()
        completer = QCompleter([a.code for a in accounts], self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self._account_names = {a.code: a.name for a in accounts}

        heading = QLabel(_KIND_TITLES[kind])
        heading.setObjectName("DialogTitle")

        self._ref = QLineEdit()
        self._ref.setPlaceholderText("PT-0001" if kind is CashKind.RECEIPT else "PC-0001")
        self._date = QDateEdit()
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("dd/MM/yyyy")
        self._date.setDate(QDate.currentDate())

        self._cash = QComboBox()
        for code, name in CASH_ACCOUNTS.items():
            self._cash.addItem(f"{code} — {name}", code)

        partner_type, default_counter, partner_label = _PARTNER_BY_KIND[kind]
        self._partner_label = partner_label

        self._counter = QLineEdit()
        self._counter.setCompleter(completer)
        self._counter.setText(default_counter)
        self._counter.setPlaceholderText("VD: 131, 331, 511, 642…")
        self._counter.textChanged.connect(self._refresh_counter_name)
        self._counter_name = QLabel("—")
        self._counter_name.setObjectName("DialogSubtitle")

        # Đối tượng công nợ: liệt kê toàn bộ khách hàng (phiếu thu) hoặc nhà cung
        # cấp (phiếu chi) để kế toán chọn đúng đối tượng thanh toán.
        self._partner = QComboBox()
        self._partner.addItem("— Không chọn —", "")
        for partner in PartnerRepository().list_all(partner_type):
            self._partner.addItem(f"{partner.code} — {partner.name}", partner.code)

        self._amount = QDoubleSpinBox()
        self._amount.setMaximum(1e15)
        self._amount.setDecimals(0)
        self._amount.setGroupSeparatorShown(True)

        self._description = QLineEdit()

        cash_label = "TK Nợ (tiền)" if kind is CashKind.RECEIPT else "TK Có (tiền)"
        counter_label = "TK Có (đối ứng)" if kind is CashKind.RECEIPT else "TK Nợ (đối ứng)"

        form = QFormLayout()
        form.addRow("Số phiếu *", self._ref)
        form.addRow("Ngày", self._date)
        form.addRow(cash_label, self._cash)
        form.addRow(counter_label, self._counter)
        form.addRow("", self._counter_name)
        form.addRow(self._partner_label, self._partner)
        form.addRow("Số tiền *", self._amount)
        form.addRow("Diễn giải", self._description)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _refresh_counter_name(self, code: str) -> None:
        self._counter_name.setText(self._account_names.get(code.strip(), "—"))

    # ----- getters ----------------------------------------------------------

    def kind(self) -> CashKind:
        return self._kind

    def ref(self) -> str:
        return self._ref.text().strip()

    def cash_account(self) -> str:
        return self._cash.currentData()

    def counter_account(self) -> str:
        return self._counter.text().strip()

    def partner_code(self) -> str:
        return self._partner.currentData() or ""

    def amount(self) -> Decimal:
        return Decimal(str(self._amount.value()))

    def entry_date(self) -> date:
        qd = self._date.date()
        return date(qd.year(), qd.month(), qd.day())

    def description(self) -> str:
        return self._description.text().strip()
