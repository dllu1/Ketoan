"""Full-width alert strip at the top of the dashboard."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.icons import icon as make_icon


class AlertStrip(QFrame):
    action_clicked = Signal()
    dismissed = Signal()

    def __init__(
        self,
        *,
        message_vi: str,
        message_en: str = "",
        action_label: str = "Xem nhiệm vụ",
        icon_name: str = "sparkle",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AlertStrip")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.setSpacing(12)

        icon = QLabel("✦")
        icon.setObjectName("AlertIcon")
        icon.setFixedSize(QSize(28, 28))
        icon.setAlignment(Qt.AlignCenter)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        vi = QLabel(message_vi)
        vi.setObjectName("AlertText")
        vi.setWordWrap(True)
        col.addWidget(vi)
        if message_en:
            en = QLabel(message_en)
            en.setObjectName("AlertTextEn")
            en.setWordWrap(True)
            col.addWidget(en)

        action = QPushButton(action_label + "  ›")
        action.setProperty("role", "btn")
        action.setProperty("variant", "ghost")
        action.setCursor(Qt.PointingHandCursor)
        action.clicked.connect(self.action_clicked.emit)

        dismiss = QPushButton()
        dismiss.setIcon(make_icon("close", color="#7e8da3"))
        dismiss.setIconSize(QSize(12, 12))
        dismiss.setFixedSize(QSize(24, 24))
        dismiss.setStyleSheet("QPushButton { background: transparent; border: none; }")
        dismiss.setCursor(Qt.PointingHandCursor)
        dismiss.clicked.connect(self.dismissed.emit)

        layout.addWidget(icon)
        layout.addLayout(col, 1)
        layout.addWidget(action)
        layout.addWidget(dismiss)
