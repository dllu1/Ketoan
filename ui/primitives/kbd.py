"""Keyboard hint labels."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class Kbd(QLabel):
    def __init__(self, key: str, parent: QWidget | None = None) -> None:
        super().__init__(key, parent)
        self.setProperty("role", "kbd")
        self.setAlignment(Qt.AlignCenter)


class KbdRow(QWidget):
    """Renders a sequence of keys like F2 · Ctrl+S · Esc."""

    def __init__(
        self,
        keys: list[str],
        *,
        spacing: int = 6,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        for key in keys:
            layout.addWidget(Kbd(key))
        layout.addStretch(1)
