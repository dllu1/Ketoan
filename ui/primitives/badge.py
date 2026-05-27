"""Badge and StatusPill labels."""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget


class BadgeTone(str, Enum):
    DEFAULT = "default"
    GOOD = "good"
    WARN = "warn"
    BAD = "bad"
    BRAND = "brand"


class StatusState(str, Enum):
    POSTED = "posted"
    DRAFT = "draft"
    REVIEW = "review"


class Badge(QLabel):
    def __init__(
        self,
        text: str,
        *,
        tone: BadgeTone = BadgeTone.DEFAULT,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text.upper(), parent)
        self.setProperty("role", "badge")
        self.setProperty("tone", tone.value)
        self.setAlignment(Qt.AlignCenter)

    def set_tone(self, tone: BadgeTone) -> None:
        self.setProperty("tone", tone.value)
        self.style().unpolish(self)
        self.style().polish(self)


class StatusPill(QLabel):
    LABELS = {
        StatusState.POSTED: "ĐÃ GHI SỔ",
        StatusState.DRAFT: "NHÁP",
        StatusState.REVIEW: "CHỜ DUYỆT",
    }

    def __init__(
        self,
        state: StatusState,
        *,
        text: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text or self.LABELS[state], parent)
        self.setProperty("role", "status-pill")
        self.setProperty("state", state.value)
        self.setAlignment(Qt.AlignCenter)

    def set_state(self, state: StatusState) -> None:
        self.setProperty("state", state.value)
        self.setText(self.LABELS[state])
        self.style().unpolish(self)
        self.style().polish(self)
