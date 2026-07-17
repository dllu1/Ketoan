"""AssetModal: create / edit a fixed asset (tài sản cố định)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from domain.models.fixed_asset import FixedAsset

_ASSET_ACCOUNTS = [("211", "211 — TSCĐ hữu hình"), ("213", "213 — TSCĐ vô hình")]
_EXPENSE_ACCOUNTS = [
    ("642", "642 — CP quản lý DN"),
    ("641", "641 — CP bán hàng"),
    ("627", "627 — CP sản xuất chung"),
]


class AssetModal(QDialog):
    def __init__(self, parent: QWidget | None = None, *, asset: FixedAsset | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AssetModal")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setWindowTitle("Tài sản mới" if asset is None else f"Sửa: {asset.name}")

        self._original = asset

        self._code = QLineEdit()
        self._name = QLineEdit()

        self._asset_account = QComboBox()
        for code, label in _ASSET_ACCOUNTS:
            self._asset_account.addItem(label, code)

        self._expense_account = QComboBox()
        for code, label in _EXPENSE_ACCOUNTS:
            self._expense_account.addItem(label, code)

        self._cost = self._money_spin()
        self._salvage = self._money_spin()

        self._life = QSpinBox()
        self._life.setRange(1, 1200)
        self._life.setValue(12)
        self._life.setSuffix(" tháng")

        self._start = QDateEdit()
        self._start.setCalendarPopup(True)
        self._start.setDisplayFormat("dd/MM/yyyy")
        self._start.setDate(QDate.currentDate())

        self._notes = QTextEdit()
        self._notes.setFixedHeight(60)

        form = QFormLayout()
        form.addRow("Mã *", self._code)
        form.addRow("Tên *", self._name)
        form.addRow("TK tài sản", self._asset_account)
        form.addRow("TK chi phí KH", self._expense_account)
        form.addRow("Nguyên giá *", self._cost)
        form.addRow("Giá trị thu hồi", self._salvage)
        form.addRow("Thời gian KH", self._life)
        form.addRow("Ngày bắt đầu", self._start)
        form.addRow("Ghi chú", self._notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if asset is not None:
            self._populate(asset)
            self._code.setReadOnly(True)

    @staticmethod
    def _money_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setMaximum(1e15)
        spin.setDecimals(0)
        spin.setGroupSeparatorShown(True)
        return spin

    def _populate(self, asset: FixedAsset) -> None:
        self._code.setText(asset.code)
        self._name.setText(asset.name)
        ai = self._asset_account.findData(asset.asset_account)
        if ai >= 0:
            self._asset_account.setCurrentIndex(ai)
        ei = self._expense_account.findData(asset.expense_account)
        if ei >= 0:
            self._expense_account.setCurrentIndex(ei)
        self._cost.setValue(float(asset.cost))
        self._salvage.setValue(float(asset.salvage_value))
        self._life.setValue(asset.useful_life_months)
        self._start.setDate(QDate(asset.start_date.year, asset.start_date.month, asset.start_date.day))
        self._notes.setPlainText(asset.notes)

    def asset(self) -> FixedAsset:
        asset = self._original or FixedAsset(code="", name="")
        asset.code = self._code.text().strip()
        asset.name = self._name.text().strip()
        asset.asset_account = self._asset_account.currentData()
        asset.expense_account = self._expense_account.currentData()
        asset.cost = Decimal(str(self._cost.value()))
        asset.salvage_value = Decimal(str(self._salvage.value()))
        asset.useful_life_months = self._life.value()
        qd = self._start.date()
        asset.start_date = date(qd.year(), qd.month(), qd.day())
        asset.notes = self._notes.toPlainText().strip()
        return asset
