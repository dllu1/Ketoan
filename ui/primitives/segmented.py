"""Segmented control: a row of mutually exclusive toggle buttons."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QWidget,
)


class Segmented(QFrame):
    selection_changed = Signal(str)

    def __init__(
        self,
        options: list[tuple[str, str]],
        *,
        default: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Segmented")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}

        for key, label in options:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("seg_key", key)
            self._group.addButton(btn)
            self._buttons[key] = btn
            layout.addWidget(btn)
            btn.clicked.connect(lambda _=False, k=key: self.selection_changed.emit(k))

        chosen = default or (options[0][0] if options else None)
        if chosen and chosen in self._buttons:
            self._buttons[chosen].setChecked(True)

    def set_active(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn:
            btn.setChecked(True)

    def active(self) -> str | None:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return None
