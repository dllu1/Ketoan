"""ItemDetailModal: chi tiết một mặt hàng trong Kho hàng (chỉ xem).

Mở bằng cách double-click một dòng ở tab Nhập–Xuất–Tồn. Gồm hai phần:

* tóm tắt kỳ đang lọc — tồn đầu kỳ / nhập / xuất / tồn cuối kỳ, lấy thẳng từ
  dòng NXT đang hiển thị nên số liệu khớp tuyệt đối với bảng phía sau;
* toàn bộ sổ phát sinh của mặt hàng (mọi kỳ), kèm cột **Tồn sau** cộng dồn để
  thấy tồn kho biến động qua từng chứng từ.
"""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from data.repositories.inventory_repo import InventoryRepository
from data.repositories.item_repo import ItemRepository
from domain.models.inventory import MovementKind, NxtRow
from domain.money import format_money
from ui.primitives.button import Button, ButtonVariant

_KIND_LABELS = {
    MovementKind.OPENING: "Tồn đầu kỳ",
    MovementKind.IN: "Nhập kho",
    MovementKind.OUT: "Xuất kho",
}

_HEADERS = [
    "Ngày", "Loại", "Chứng từ", "Số lượng", "Đơn giá", "Thành tiền",
    "Tồn sau", "Diễn giải",
]
(_C_DATE, _C_KIND, _C_REF, _C_QTY, _C_PRICE, _C_VALUE, _C_ONHAND, _C_NOTE) = range(8)


class ItemDetailModal(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        item_code: str,
        nxt_row: NxtRow | None = None,
        period_label: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ItemDetailModal")
        self.setModal(True)
        self.setMinimumSize(880, 560)

        item = ItemRepository().find_by_code(item_code)
        movements = InventoryRepository().list_for_item(item_code)
        name = (item.name if item else "") or (nxt_row.item_name if nxt_row else "")
        unit = (item.unit if item else "") or (nxt_row.unit if nxt_row else "")
        account = (
            (nxt_row.account_code if nxt_row else "")
            or (item.account_code if item else "")
        )
        self.setWindowTitle(f"Chi tiết: {item_code}")

        header = QFrame()
        header.setObjectName("DialogHeader")
        hf = QVBoxLayout(header)
        hf.setContentsMargins(0, 0, 0, 12)
        hf.setSpacing(2)
        title = QLabel(f"{item_code} — {name}" if name else item_code)
        title.setObjectName("DialogTitle")
        details = " · ".join(
            part for part in (
                f"ĐVT {unit}" if unit else "",
                f"Kho {account}" if account else "",
                f"Kỳ lọc {period_label}" if period_label else "",
                f"{len(movements)} lượt phát sinh",
            ) if part
        )
        subtitle = QLabel(details)
        subtitle.setObjectName("DialogSubtitle")
        hf.addWidget(title)
        hf.addWidget(subtitle)

        summary = QLabel(_summary_text(nxt_row))
        summary.setObjectName("BalanceBar")
        summary.setWordWrap(True)

        table = QTableWidget(0, len(_HEADERS))
        table.setHorizontalHeaderLabels(_HEADERS)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        head = table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeToContents)
        head.setSectionResizeMode(_C_NOTE, QHeaderView.Stretch)
        _fill_movements(table, movements)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        btn_close = Button("Đóng", variant=ButtonVariant.GHOST)
        btn_close.clicked.connect(self.accept)
        close_row.addWidget(btn_close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addWidget(header)
        layout.addWidget(summary)
        layout.addWidget(table, 1)
        layout.addLayout(close_row)


def _summary_text(row: NxtRow | None) -> str:
    if row is None:
        return "Chưa có số liệu Nhập–Xuất–Tồn cho kỳ đang lọc."
    return (
        f"Tồn đầu kỳ {_qty(row.opening_qty)} · {format_money(row.opening_value)}    "
        f"Nhập {_qty(row.in_qty)} · {format_money(row.in_value)}    "
        f"Xuất {_qty(row.out_qty)} · {format_money(row.out_value)}    "
        f"TỒN CUỐI {_qty(row.closing_qty)} · {format_money(row.closing_value)}"
    )


def _fill_movements(table: QTableWidget, movements) -> None:
    """Đổ sổ phát sinh, cộng dồn tồn kho sau mỗi lượt (sổ đã sắp theo ngày)."""
    on_hand = Decimal("0")
    for movement in movements:
        on_hand += movement.signed_quantity
        row = table.rowCount()
        table.insertRow(row)
        cells = [
            movement.move_date.strftime("%d/%m/%Y"),
            _KIND_LABELS.get(movement.kind, movement.kind.value),
            movement.source_ref,
            _qty(movement.quantity),
            format_money(movement.unit_cost),
            format_money(movement.value),
            _qty(on_hand),
            movement.note,
        ]
        for col, value in enumerate(cells):
            cell = QTableWidgetItem(value)
            if col in (_C_QTY, _C_PRICE, _C_VALUE, _C_ONHAND):
                cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(row, col, cell)


def _qty(value: Decimal) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".") if value else "0"
