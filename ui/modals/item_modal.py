"""ItemModal: create / edit a material/tool/good record."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from domain.models.item import Item, ItemCategory


class ItemModal(QDialog):
    def __init__(self, parent: QWidget | None = None, *, item: Item | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ItemModal")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setWindowTitle("Vật tư mới" if item is None else f"Sửa: {item.name}")

        self._original = item

        self._code = QLineEdit()
        self._name = QLineEdit()

        self._category = QComboBox()
        for cat in ItemCategory:
            self._category.addItem(self._category_label(cat), cat)

        self._unit = QLineEdit("Cái")

        self._unit_price = QDoubleSpinBox()
        self._unit_price.setMaximum(1e12)
        self._unit_price.setDecimals(2)
        self._unit_price.setGroupSeparatorShown(True)

        self._vat = QComboBox()
        for rate in (0, 5, 8, 10):
            self._vat.addItem(f"{rate}%", Decimal(rate))

        self._account = QLineEdit()
        self._notes = QTextEdit()
        self._notes.setFixedHeight(60)

        form = QFormLayout()
        form.addRow("Mã *", self._code)
        form.addRow("Tên *", self._name)
        form.addRow("Nhóm", self._category)
        form.addRow("ĐVT", self._unit)
        form.addRow("Đơn giá", self._unit_price)
        form.addRow("VAT", self._vat)
        form.addRow("Tài khoản kế toán", self._account)
        form.addRow("Ghi chú", self._notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if item is not None:
            self._populate(item)
            self._code.setReadOnly(True)

    @staticmethod
    def _category_label(cat: ItemCategory) -> str:
        return {
            ItemCategory.MATERIAL: "152 — Nguyên vật liệu",
            ItemCategory.TOOL: "153 — Công cụ dụng cụ",
            ItemCategory.PRODUCT: "155 — Thành phẩm",
            ItemCategory.GOOD: "156 — Hàng hóa",
        }[cat]

    def _populate(self, item: Item) -> None:
        self._code.setText(item.code)
        self._name.setText(item.name)
        idx = self._category.findData(item.category)
        if idx >= 0:
            self._category.setCurrentIndex(idx)
        self._unit.setText(item.unit)
        self._unit_price.setValue(float(item.unit_price))
        vat_idx = self._vat.findData(item.vat_rate)
        if vat_idx >= 0:
            self._vat.setCurrentIndex(vat_idx)
        self._account.setText(item.account_code)
        self._notes.setPlainText(item.notes)

    def item(self) -> Item:
        item = self._original or Item(code="", name="")
        item.code = self._code.text().strip()
        item.name = self._name.text().strip()
        item.category = self._category.currentData()
        item.unit = self._unit.text().strip() or "Cái"
        item.unit_price = Decimal(str(self._unit_price.value()))
        item.vat_rate = self._vat.currentData()
        item.account_code = self._account.text().strip() or item.category.value
        item.notes = self._notes.toPlainText().strip()
        return item
