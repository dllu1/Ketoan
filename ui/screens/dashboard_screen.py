"""Dashboard placeholder for Phase 1."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class DashboardScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DashboardScreen")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)

        title = QLabel("Tổng quan")
        title.setObjectName("ScreenTitle")
        subtitle = QLabel(
            "Hưng Phát · Phần mềm kế toán theo Thông tư 200/TT-BTC\n"
            "Phase 1: hoàn thành Chrome window + Danh mục đối tác/vật tư."
        )
        subtitle.setObjectName("ScreenSubtitle")
        subtitle.setAlignment(Qt.AlignLeft)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch(1)
