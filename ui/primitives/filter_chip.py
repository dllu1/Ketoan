"""Filter chip: a checkable pill with optional count suffix."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget


class FilterChip(QPushButton):
    def __init__(
        self,
        text: str,
        *,
        count: int | None = None,
        checked: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = text
        self._count = count
        self.setProperty("role", "filter-chip")
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self._refresh_text()

    def set_count(self, count: int | None) -> None:
        self._count = count
        self._refresh_text()

    def set_label(self, text: str) -> None:
        self._label = text
        self._refresh_text()

    def _refresh_text(self) -> None:
        if self._count is None:
            self.setText(self._label)
        else:
            self.setText(f"{self._label}  ·  {self._count}")
