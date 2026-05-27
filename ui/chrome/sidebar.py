"""Module navigation sidebar (Mode A: full labels)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class Sidebar(QWidget):
    WIDTH = 220

    module_selected = Signal(str)

    MODULES: tuple[tuple[str, str, str], ...] = (
        ("dashboard", "Tổng quan", "F2"),
        ("sales", "Bán hàng", "F3"),
        ("purchase", "Mua hàng", "F4"),
        ("inventory", "Kho - NXT", "F5"),
        ("journal", "Sổ nhật ký", "F6"),
        ("assets", "TSCĐ", "F7"),
        ("reports", "Báo cáo", "F8"),
        ("directory", "Danh mục", "F9"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(self.WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(2)

        self._buttons: dict[str, QPushButton] = {}
        for key, label, shortcut in self.MODULES:
            btn = QPushButton(f"  {label}")
            btn.setObjectName("SidebarItem")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setMinimumHeight(34)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("shortcut_hint", shortcut)
            btn.clicked.connect(lambda _=False, k=key: self.module_selected.emit(k))
            self._buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch(1)

    def set_active(self, module_key: str) -> None:
        btn = self._buttons.get(module_key)
        if btn:
            btn.setChecked(True)
