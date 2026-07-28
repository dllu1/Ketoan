"""AccountModal: create / edit a chart-of-accounts entry."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from domain.models.account import Account, AccountKind

_KIND_LABELS = {
    AccountKind.ASSET: "Tài sản",
    AccountKind.LIABILITY: "Nợ phải trả",
    AccountKind.EQUITY: "Vốn chủ sở hữu",
    AccountKind.REVENUE: "Doanh thu",
    AccountKind.EXPENSE: "Chi phí",
    AccountKind.OTHER: "Khác",
}

_NO_PARENT = "— Không (tài khoản độc lập) —"


class AccountModal(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        account: Account | None = None,
        accounts: list[Account] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AccountModal")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setWindowTitle("Tài khoản mới" if account is None else f"Sửa: {account.code}")

        self._original = account

        self._code = QLineEdit()
        self._name = QLineEdit()
        self._kind = QComboBox()
        for kind in AccountKind:
            self._kind.addItem(_KIND_LABELS[kind], kind.value)

        # Tài khoản tổng hợp (cha): số dư của TK này sẽ được cộng dồn vào TK cha
        # trong danh mục và các báo cáo. Loại chính nó khỏi danh sách để tránh tự
        # trỏ; vòng lặp sâu hơn do AccountService bắt và báo lỗi khi Lưu.
        self._parent = QComboBox()
        self._parent.addItem(_NO_PARENT, "")
        own_code = account.code if account is not None else None
        for acc in accounts or []:
            if acc.code == own_code:
                continue
            self._parent.addItem(f"{acc.code} — {acc.name}", acc.code)

        self._active = QCheckBox("Đang hoạt động")
        self._active.setChecked(True)

        form = QFormLayout()
        form.addRow("Mã *", self._code)
        form.addRow("Tên TK *", self._name)
        form.addRow("Loại", self._kind)
        form.addRow("Thuộc TK tổng hợp", self._parent)
        form.addRow("", self._active)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if account is not None:
            self._populate(account)
            self._code.setReadOnly(True)

    def _populate(self, account: Account) -> None:
        self._code.setText(account.code)
        self._name.setText(account.name)
        idx = self._kind.findData(account.kind)
        if idx >= 0:
            self._kind.setCurrentIndex(idx)
        parent_idx = self._parent.findData(account.parent_code)
        self._parent.setCurrentIndex(parent_idx if parent_idx >= 0 else 0)
        self._active.setChecked(account.active)

    def account(self) -> Account:
        account = self._original or Account(code="", name="")
        account.code = self._code.text().strip()
        account.name = self._name.text().strip()
        account.kind = self._kind.currentData()
        account.parent_code = self._parent.currentData() or ""
        account.active = self._active.isChecked()
        return account
