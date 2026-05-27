"""Card container with optional header (title + action area)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class CardHeader(QFrame):
    def __init__(
        self,
        title: str,
        *,
        subtitle: str | None = None,
        action: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CardHeader")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self._title = QLabel(title)
        self._title.setObjectName("CardTitle")
        text_col.addWidget(self._title)

        if subtitle:
            self._subtitle: QLabel | None = QLabel(subtitle)
            self._subtitle.setObjectName("CardSubtitle")
            text_col.addWidget(self._subtitle)
        else:
            self._subtitle = None

        layout.addLayout(text_col, 1)

        if action is not None:
            layout.addWidget(action, alignment=Qt.AlignRight)

    def set_title(self, title: str) -> None:
        self._title.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        if self._subtitle:
            self._subtitle.setText(subtitle)


class Card(QFrame):
    """Card with stacked CardHeader + content area."""

    def __init__(
        self,
        *,
        title: str | None = None,
        subtitle: str | None = None,
        action: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        self._header: CardHeader | None = None
        if title:
            self._header = CardHeader(title, subtitle=subtitle, action=action)
            self._outer.addWidget(self._header)

        self._body = QFrame()
        self._body.setObjectName("CardBody")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(16, 12, 16, 16)
        self._body_layout.setSpacing(8)
        self._outer.addWidget(self._body, 1)

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self._body_layout.addWidget(widget, stretch)

    def add_layout(self, layout) -> None:
        self._body_layout.addLayout(layout)
