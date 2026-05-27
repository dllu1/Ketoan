"""Monochrome donut chart with center label."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui.tokens import active_tokens


@dataclass
class DonutSegment:
    label_vi: str
    label_en: str
    pct: float           # 0..100


class Donut(QWidget):
    def __init__(
        self,
        data: list[DonutSegment],
        *,
        size: int = 180,
        center_label: str = "TỔNG CHI",
        center_value: str = "",
        center_sub: str = "VND · MTD",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data = data
        self._size = size
        self._center_label = center_label
        self._center_value = center_value
        self._center_sub = center_sub
        self.setMinimumSize(size, size)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_center_value(self, value: str) -> None:
        self._center_value = value
        self.update()

    # Monochrome scale derived from brand (steps toward darker brand_900).
    def _segment_color(self, index: int, total: int) -> QColor:
        tokens = active_tokens()
        scale = (
            tokens.brand,
            tokens.brand_400,
            tokens.brand_600,
            tokens.brand_700,
            tokens.brand_800,
            tokens.brand_900,
        )
        idx = min(index, len(scale) - 1)
        return QColor(scale[idx])

    def paintEvent(self, _event) -> None:
        if not self._data:
            return
        tokens = active_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        size = min(self.width(), self.height())
        stroke = 18
        r = size / 2 - 14
        cx = self.width() / 2
        cy = self.height() / 2

        total = sum(s.pct for s in self._data) or 1.0
        start_angle = 90.0  # Qt uses degrees, 0=3 o'clock, anticlockwise; we want top start

        for i, seg in enumerate(self._data):
            span = (seg.pct / total) * 360.0
            color = self._segment_color(i, len(self._data))
            pen = QPen(color)
            pen.setWidthF(stroke)
            pen.setCapStyle(Qt.FlatCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
            # Qt drawArc uses 1/16ths of a degree, anticlockwise positive
            painter.drawArc(rect, int(start_angle * 16), int(-span * 16))
            start_angle -= span

        # center text
        painter.setPen(QColor(tokens.txt_3))
        font_small = QFont(tokens.font_family, 8)
        font_small.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
        painter.setFont(font_small)
        painter.drawText(
            QRectF(0, cy - 26, self.width(), 14),
            Qt.AlignCenter,
            self._center_label,
        )

        if self._center_value:
            painter.setPen(QColor(tokens.txt))
            font_big = QFont(tokens.font_family, 16)
            font_big.setBold(True)
            painter.setFont(font_big)
            painter.drawText(
                QRectF(0, cy - 12, self.width(), 22),
                Qt.AlignCenter,
                self._center_value,
            )

        painter.setPen(QColor(tokens.txt_3))
        painter.setFont(font_small)
        painter.drawText(
            QRectF(0, cy + 14, self.width(), 14),
            Qt.AlignCenter,
            self._center_sub,
        )

        painter.end()

    def segment_color_hex(self, index: int) -> str:
        return self._segment_color(index, len(self._data)).name()
