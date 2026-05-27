"""Empty state for modules not yet built."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ui.icons import icon as make_icon


class EmptyState(QFrame):
    def __init__(
        self,
        title: str,
        *,
        hint: str = "",
        icon_name: str = "sparkle",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyState")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel()
        icon_label.setPixmap(make_icon(icon_name).pixmap(QSize(48, 48)))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border: none;")

        title_label = QLabel(title)
        title_label.setObjectName("EmptyTitle")
        title_label.setAlignment(Qt.AlignCenter)

        layout.addStretch(1)
        layout.addWidget(icon_label)
        layout.addWidget(title_label)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("EmptyHint")
            hint_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(hint_label)
        layout.addStretch(2)
