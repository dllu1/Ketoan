"""StockModal: record an inbound inventory movement (Tồn đầu kỳ / Nhập kho).

Per the form notes, when a finished product (kho 155) is received the amount
comes from its computed giá thành: selecting a 155 item with kind "Nhập kho"
auto-fills Đơn giá from the active period's costing sheet (still editable).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from app.period import active_period
from data.repositories.costing_repo import CostingRepository
from data.repositories.item_repo import ItemRepository
from domain.models.inventory import MovementKind
from domain.services.costing_service import CostingService

_KIND_LABELS = {
    MovementKind.IN: "Nhập kho",
    MovementKind.OPENING: "Tồn đầu kỳ",
}


class StockModal(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StockModal")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setWindowTitle("Nhập kho")

        self._items = ItemRepository().list_all()
        self._by_code = {it.code: it for it in self._items}
        self._unit_costs = self._load_unit_costs()

        self._item = QComboBox()
        for it in self._items:
            self._item.addItem(f"{it.code} — {it.name}", it.code)
        self._item.currentIndexChanged.connect(self._auto_fill_cost)

        self._kind = QComboBox()
        for kind in (MovementKind.IN, MovementKind.OPENING):
            self._kind.addItem(_KIND_LABELS[kind], kind)
        self._kind.currentIndexChanged.connect(self._auto_fill_cost)

        self._date = QDateEdit()
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("dd/MM/yyyy")
        self._date.setDate(QDate.currentDate())

        self._quantity = QDoubleSpinBox()
        self._quantity.setMaximum(1e12)
        self._quantity.setDecimals(2)
        self._quantity.setGroupSeparatorShown(True)

        self._unit_cost = QDoubleSpinBox()
        self._unit_cost.setMaximum(1e12)
        self._unit_cost.setDecimals(0)
        self._unit_cost.setGroupSeparatorShown(True)

        self._cost_hint = QLabel()
        self._cost_hint.setWordWrap(True)

        self._note = QLineEdit()

        form = QFormLayout()
        form.addRow("Mặt hàng *", self._item)
        form.addRow("Loại", self._kind)
        form.addRow("Ngày", self._date)
        form.addRow("Số lượng *", self._quantity)
        form.addRow("Đơn giá", self._unit_cost)
        form.addRow("", self._cost_hint)
        form.addRow("Ghi chú", self._note)
        self._auto_fill_cost()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    # ----- giá thành auto-fill (nhập kho thành phẩm 155) -------------------

    def _load_unit_costs(self) -> dict[str, Decimal]:
        """Đơn giá giá thành theo mã SP từ bảng tính giá thành của kỳ."""
        try:
            sheet = CostingService(CostingRepository()).load(active_period().key)
        except Exception:
            return {}
        return {
            r.code.strip(): r.unit_cost
            for r in sheet.rows
            if r.code.strip() and r.unit_cost > 0
        }

    def _auto_fill_cost(self) -> None:
        code = self._item.currentData() or ""
        item = self._by_code.get(code)
        cost = self._unit_costs.get(code)
        is_product_in = (
            item is not None
            and item.account_code.startswith("155")
            # Coerce: Qt returns str-based enum userData as a plain str.
            and MovementKind(self._kind.currentData()) is MovementKind.IN
        )
        if is_product_in and cost:
            self._unit_cost.setValue(float(cost))
            self._cost_hint.setText(
                f"Đơn giá lấy từ Giá thành SP kỳ {active_period().label} "
                "(có thể sửa)."
            )
        else:
            self._cost_hint.setText("")

    @property
    def has_items(self) -> bool:
        return bool(self._items)

    def item_code(self) -> str:
        return self._item.currentData() or ""

    def kind(self) -> MovementKind:
        # Coerce: Qt returns str-based enum userData as a plain str.
        return MovementKind(self._kind.currentData())

    def move_date(self) -> date:
        qd = self._date.date()
        return date(qd.year(), qd.month(), qd.day())

    def quantity(self) -> Decimal:
        return Decimal(str(self._quantity.value()))

    def unit_cost(self) -> Decimal:
        return Decimal(str(self._unit_cost.value()))

    def note(self) -> str:
        return self._note.text().strip()
