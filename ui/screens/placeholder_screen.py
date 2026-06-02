"""PlaceholderScreen: stub for modules built in a later phase."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.icons import icon as make_icon
from ui.primitives.badge import Badge


class PlaceholderScreen(QWidget):
    def __init__(
        self,
        *,
        title_vi: str,
        title_en: str,
        icon_name: str,
        phase: str,
    ) -> None:
        super().__init__()
        self.setObjectName("PlaceholderScreen")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setPixmap(make_icon(icon_name, color="#7e8da3").pixmap(QSize(48, 48)))
        icon_label.setAlignment(Qt.AlignCenter)

        title = QLabel(title_vi)
        title.setObjectName("ScreenTitle")
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel(title_en.upper())
        subtitle.setObjectName("PlaceholderLabel")
        subtitle.setAlignment(Qt.AlignCenter)

        badge = Badge(phase)

        layout.addWidget(icon_label)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(badge, alignment=Qt.AlignCenter)
