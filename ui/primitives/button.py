"""Button primitive matching the .btn class family from the design system."""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

from ui.icons import icon as make_icon


class ButtonVariant(str, Enum):
    DEFAULT = "default"
    PRIMARY = "primary"
    GHOST = "ghost"
    DANGER = "danger"


class ButtonSize(str, Enum):
    SM = "sm"
    MD = "md"


class Button(QPushButton):
    def __init__(
        self,
        text: str = "",
        *,
        variant: ButtonVariant = ButtonVariant.DEFAULT,
        size: ButtonSize = ButtonSize.MD,
        icon_name: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setProperty("role", "btn")
        self.setProperty("variant", variant.value)
        self.setProperty("size", size.value)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        if icon_name:
            self.setIcon(make_icon(icon_name))
            self.setIconSize(QSize(16, 16))

    def set_variant(self, variant: ButtonVariant) -> None:
        self.setProperty("variant", variant.value)
        self.style().unpolish(self)
        self.style().polish(self)
