"""12-month area + line chart with grid, axis labels, and hover crosshair."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui.tokens import active_tokens


class TrendView(str, Enum):
    ALL = "all"
    REVENUE = "rev"
    COST = "cost"
    OPEX = "opex"


@dataclass
class TrendPoint:
    month: str           # e.g. "02/25"
    revenue: float       # in VND (raw)
    cost: float
    opex: float

    def value(self, key: str) -> float:
        if key == "rev":
            return self.revenue
        if key == "cost":
            return self.cost
        if key == "opex":
            return self.opex
        return self.revenue


class TrendChart(QWidget):
    PAD_L = 56
    PAD_R = 12
    PAD_T = 16
    PAD_B = 26

    def __init__(
        self,
        data: list[TrendPoint],
        *,
        view: TrendView = TrendView.ALL,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data = data
        self._view = view
        self._hover_index: int | None = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(220)
        self.setMouseTracking(True)

    def set_view(self, view: TrendView) -> None:
        self._view = view
        self.update()

    def set_data(self, data: list[TrendPoint]) -> None:
        self._data = data
        self.update()

    # ---- geometry ---------------------------------------------------------

    def _inner_rect(self) -> QRectF:
        return QRectF(
            self.PAD_L,
            self.PAD_T,
            self.width() - self.PAD_L - self.PAD_R,
            self.height() - self.PAD_T - self.PAD_B,
        )

    def _max_value(self) -> float:
        max_v = 0.0
        for p in self._data:
            max_v = max(max_v, p.revenue, p.cost, p.opex)
        return (max_v or 1.0) * 1.1

    def _x_for(self, i: int) -> float:
        rect = self._inner_rect()
        if len(self._data) < 2:
            return rect.left()
        return rect.left() + (rect.width() * i) / (len(self._data) - 1)

    def _y_for(self, value: float, max_v: float) -> float:
        rect = self._inner_rect()
        return rect.top() + rect.height() - (value / max_v) * rect.height()

    # ---- painting ---------------------------------------------------------

    def paintEvent(self, _event) -> None:
        if not self._data:
            return
        tokens = active_tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self._inner_rect()
        max_v = self._max_value()

        self._draw_grid(painter, rect, max_v, tokens)
        self._draw_axis(painter, rect, max_v, tokens)

        if self._view == TrendView.ALL:
            self._draw_series(painter, "rev", rect, max_v, tokens, fill=True, dashed=False)
            self._draw_series(painter, "cost", rect, max_v, tokens, fill=False, dashed=True)
        else:
            self._draw_series(painter, self._view.value, rect, max_v, tokens, fill=True, dashed=False)

        self._draw_points(painter, rect, max_v, tokens)
        self._draw_hover(painter, rect, tokens)

        painter.end()

    def _draw_grid(self, p: QPainter, rect: QRectF, max_v: float, tokens) -> None:
        pen = QPen(QColor(tokens.line))
        pen.setWidthF(1)
        pen.setDashPattern([2, 4])
        p.setPen(pen)
        for ratio in (0.25, 0.5, 0.75, 1.0):
            y = rect.top() + rect.height() - rect.height() * ratio
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

    def _draw_axis(self, p: QPainter, rect: QRectF, max_v: float, tokens) -> None:
        p.setPen(QColor(tokens.txt_4))
        font = QFont(tokens.font_family, 8)
        font.setStyleHint(QFont.Monospace)
        p.setFont(font)

        # Y axis labels (formatted as tỷ / tr)
        for ratio in (0.25, 0.5, 0.75, 1.0):
            y = rect.top() + rect.height() - rect.height() * ratio
            value = max_v * ratio
            label = _format_vnd_short(value)
            p.drawText(
                QRectF(0, y - 8, self.PAD_L - 6, 16),
                Qt.AlignRight | Qt.AlignVCenter,
                label,
            )

        # X axis labels
        for i, point in enumerate(self._data):
            x = self._x_for(i)
            p.drawText(
                QRectF(x - 25, rect.bottom() + 4, 50, self.PAD_B - 4),
                Qt.AlignCenter | Qt.AlignTop,
                point.month,
            )

    def _draw_series(
        self,
        p: QPainter,
        key: str,
        rect: QRectF,
        max_v: float,
        tokens,
        *,
        fill: bool,
        dashed: bool,
    ) -> None:
        brand = QColor(tokens.brand)

        # build path
        path = QPainterPath()
        for i, point in enumerate(self._data):
            pt = QPointF(self._x_for(i), self._y_for(point.value(key), max_v))
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)

        # area fill
        if fill:
            area = QPainterPath(path)
            area.lineTo(QPointF(self._x_for(len(self._data) - 1), rect.bottom()))
            area.lineTo(QPointF(self._x_for(0), rect.bottom()))
            area.closeSubpath()

            grad = QLinearGradient(
                QPointF(0, rect.top()), QPointF(0, rect.bottom())
            )
            top = QColor(brand)
            top.setAlphaF(0.30)
            bot = QColor(brand)
            bot.setAlphaF(0.0)
            grad.setColorAt(0.0, top)
            grad.setColorAt(1.0, bot)

            p.setBrush(grad)
            p.setPen(Qt.NoPen)
            p.drawPath(area)

        # line stroke
        pen = QPen(brand if not dashed else QColor(tokens.brand_700))
        pen.setWidthF(1.6)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        if dashed:
            pen.setDashPattern([3, 3])
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    def _draw_points(self, p: QPainter, rect: QRectF, max_v: float, tokens) -> None:
        key = "rev" if self._view == TrendView.ALL else self._view.value
        brand = QColor(tokens.brand)
        panel = QColor(tokens.panel_solid)
        pen = QPen(brand)
        pen.setWidthF(1.2)
        for i, point in enumerate(self._data):
            x = self._x_for(i)
            y = self._y_for(point.value(key), max_v)
            r = 3.5 if self._hover_index == i else 2.2
            p.setPen(pen)
            p.setBrush(brand if self._hover_index == i else panel)
            p.drawEllipse(QPointF(x, y), r, r)

    def _draw_hover(self, p: QPainter, rect: QRectF, tokens) -> None:
        if self._hover_index is None:
            return
        x = self._x_for(self._hover_index)
        pen = QPen(QColor(tokens.brand))
        pen.setWidthF(1)
        pen.setDashPattern([3, 3])
        p.setPen(pen)
        p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

        # tooltip
        point = self._data[self._hover_index]
        key = "rev" if self._view == TrendView.ALL else self._view.value
        value = point.value(key)
        text = f"Kỳ {point.month}\n{_format_vnd_full(value)}"

        font = QFont(tokens.font_family, 9)
        p.setFont(font)

        metrics = p.fontMetrics()
        lines = text.splitlines()
        text_w = max(metrics.horizontalAdvance(line) for line in lines)
        text_h = metrics.height() * len(lines)
        pad = 8
        box_w = text_w + pad * 2
        box_h = text_h + pad

        tip_x = min(max(x - box_w / 2, rect.left()), rect.right() - box_w)
        tip_y = self._y_for(value, self._max_value()) - box_h - 10
        tip_y = max(tip_y, rect.top())

        bg = QColor(tokens.panel_solid)
        border = QColor(tokens.line_strong)
        p.setBrush(bg)
        p.setPen(QPen(border, 1))
        p.drawRoundedRect(QRectF(tip_x, tip_y, box_w, box_h), 6, 6)

        p.setPen(QColor(tokens.txt))
        p.drawText(
            QRectF(tip_x + pad, tip_y + pad / 2, text_w, text_h),
            Qt.AlignLeft | Qt.AlignTop,
            text,
        )

    # ---- interaction ------------------------------------------------------

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        rect = self._inner_rect()
        x = event.position().x()
        if x < rect.left() or x > rect.right() or len(self._data) < 2:
            self._hover_index = None
        else:
            ratio = (x - rect.left()) / rect.width()
            idx = round(ratio * (len(self._data) - 1))
            self._hover_index = max(0, min(len(self._data) - 1, idx))
        self.update()

    def leaveEvent(self, _event) -> None:
        self._hover_index = None
        self.update()


def _format_vnd_short(value: float) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} tỷ"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.0f} tr"
    if value >= 1_000:
        return f"{value / 1_000:.0f} ng"
    return f"{value:.0f}"


def _format_vnd_full(value: float) -> str:
    return f"{value:,.0f} ₫".replace(",", ".")
