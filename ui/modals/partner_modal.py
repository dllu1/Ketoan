"""PartnerModal: create / edit a partner record."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from domain.models.partner import Partner, PartnerType


class PartnerModal(QDialog):
    def __init__(self, parent: QWidget | None = None, *, partner: Partner | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PartnerModal")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setWindowTitle("Đối tác mới" if partner is None else f"Sửa: {partner.name}")

        self._original = partner

        self._code = QLineEdit()
        self._name = QLineEdit()
        self._type = QComboBox()
        for pt in PartnerType:
            self._type.addItem(self._type_label(pt), pt)
        self._tax_code = QLineEdit()
        self._phone = QLineEdit()
        self._email = QLineEdit()
        self._contact = QLineEdit()
        self._bank_account = QLineEdit()
        self._bank_name = QLineEdit()
        self._address = QTextEdit()
        self._address.setFixedHeight(60)
        self._notes = QTextEdit()
        self._notes.setFixedHeight(60)

        form = QFormLayout()
        form.addRow("Mã *", self._code)
        form.addRow("Tên *", self._name)
        form.addRow("Loại", self._type)
        form.addRow("MST", self._tax_code)
        form.addRow("Người liên hệ", self._contact)
        form.addRow("Điện thoại", self._phone)
        form.addRow("Email", self._email)
        form.addRow("Số tài khoản", self._bank_account)
        form.addRow("Ngân hàng", self._bank_name)
        form.addRow("Địa chỉ", self._address)
        form.addRow("Ghi chú", self._notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if partner is not None:
            self._populate(partner)
            self._code.setReadOnly(True)

    @staticmethod
    def _type_label(pt: PartnerType) -> str:
        return {
            PartnerType.CUSTOMER: "Khách hàng",
            PartnerType.SUPPLIER: "Nhà cung cấp",
            PartnerType.BOTH: "Cả hai",
        }[pt]

    def _populate(self, partner: Partner) -> None:
        self._code.setText(partner.code)
        self._name.setText(partner.name)
        index = self._type.findData(partner.type)
        if index >= 0:
            self._type.setCurrentIndex(index)
        self._tax_code.setText(partner.tax_code)
        self._phone.setText(partner.phone)
        self._email.setText(partner.email)
        self._contact.setText(partner.contact_person)
        self._bank_account.setText(partner.bank_account)
        self._bank_name.setText(partner.bank_name)
        self._address.setPlainText(partner.address)
        self._notes.setPlainText(partner.notes)

    def partner(self) -> Partner:
        partner = self._original or Partner(code="", name="")
        partner.code = self._code.text().strip()
        partner.name = self._name.text().strip()
        # Coerce: Qt returns str-based enum userData as a plain str.
        partner.type = PartnerType(self._type.currentData())
        partner.tax_code = self._tax_code.text().strip()
        partner.phone = self._phone.text().strip()
        partner.email = self._email.text().strip()
        partner.contact_person = self._contact.text().strip()
        partner.bank_account = self._bank_account.text().strip()
        partner.bank_name = self._bank_name.text().strip()
        partner.address = self._address.toPlainText().strip()
        partner.notes = self._notes.toPlainText().strip()
        return partner
