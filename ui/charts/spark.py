"""Tiny line+dot sparkline (80×28) for KPI cards."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ui.tokens import active_tokens


class Spark(QWidget):
    def __init__(
        self,
        data: list[float],
        *,
        width: int = 80,
        height: int = 28,
        positive: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data = list(data)
        self._positive = positive
        self.setFixedSize(QSize(width, height))
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_data(self, data: list[float]) -> None:
        self._data = list(data)
        self.update()

    def paintEvent(self, _event) -> None:
        if len(self._data) < 2:
            return

        tokens = active_tokens()
        stroke = QColor(tokens.brand if self._positive else tokens.bad)

        w = self.width()
        h = self.height()
        max_v = max(self._data)
        min_v = min(self._data)
        span = max_v - min_v or 1.0
        n = len(self._data)

        points: list[QPointF] = []
        for i, v in enumerate(self._data):
            x = (i / (n - 1)) * (w - 2) + 1
            y = h - 2 - ((v - min_v) / span) * (h - 4)
            points.append(QPointF(x, y))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        pen = QPen(stroke)
        pen.setWidthF(1.4)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])

        # end dot
        painter.setBrush(stroke)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(points[-1], 2.2, 2.2)
        painter.end()
