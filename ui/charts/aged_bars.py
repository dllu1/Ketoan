"""Horizontal aged receivables bars (brand → warn → bad gradient)."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui.tokens import active_tokens


@dataclass
class AgedBucket:
    bucket_vi: str
    bucket_en: str
    amount: float


class AgedBars(QWidget):
    ROW_HEIGHT = 44
    TEXT_HEIGHT = 18
    BAR_HEIGHT = 6
    BAR_TOP_OFFSET = 24

    def __init__(
        self,
        data: list[AgedBucket],
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data = data
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(self.ROW_HEIGHT * max(1, len(data)))
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def sizeHint(self) -> QSize:
        return QSize(280, self.ROW_HEIGHT * max(1, len(self._data)))

    def paintEvent(self, _event) -> None:
        if not self._data:
            return
        tokens = active_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        font = QFont(tokens.font_family, 9)
        painter.setFont(font)

        max_amount = max(b.amount for b in self._data) or 1.0
        colors = (tokens.brand, tokens.brand_600, tokens.warn, tokens.bad)

        w = self.width()
        y = 0
        for i, bucket in enumerate(self._data):
            self._draw_row(painter, bucket, i, colors, max_amount, w, y, tokens)
            y += self.ROW_HEIGHT
        painter.end()

    def _draw_row(self, p, bucket, index, colors, max_amount, w, y, tokens) -> None:
        # ---- text row
        label_text = f"{bucket.bucket_vi} · {bucket.bucket_en}"
        amount_text = _format_vnd_compact(bucket.amount)

        p.setPen(QColor(tokens.txt_2))
        p.drawText(
            QRectF(0, y, w * 0.65, self.TEXT_HEIGHT),
            Qt.AlignLeft | Qt.AlignVCenter,
            label_text,
        )

        p.setPen(QColor(tokens.txt))
        font = p.font()
        font.setBold(True)
        p.setFont(font)
        p.drawText(
            QRectF(w * 0.45, y, w * 0.55, self.TEXT_HEIGHT),
            Qt.AlignRight | Qt.AlignVCenter,
            amount_text,
        )
        font.setBold(False)
        p.setFont(font)

        # ---- bar
        ratio = bucket.amount / max_amount
        bar_y = y + self.BAR_TOP_OFFSET
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(tokens.card_2))
        p.drawRoundedRect(QRectF(0, bar_y, w, self.BAR_HEIGHT), 3, 3)
        color_idx = min(index, len(colors) - 1)
        p.setBrush(QColor(colors[color_idx]))
        p.drawRoundedRect(QRectF(0, bar_y, w * ratio, self.BAR_HEIGHT), 3, 3)


def _format_vnd_compact(value: float) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} tỷ"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} tr"
    if value >= 1_000:
        return f"{value / 1_000:.0f} ng"
    return f"{value:.0f}"
