"""Icon registry: line-style 18px icons drawn via QPainter.

Each icon is a callable that receives a QPainter and a unit rectangle and
draws strokes in `currentColor`. Wrapped in a QIcon via an engine so widgets
can use them with QPushButton(icon, "Label").
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QIconEngine,
    QPainter,
    QPen,
    QPixmap,
)

from ui.tokens import active_tokens

Drawer = Callable[[QPainter, QRectF], None]


# ----- low-level helpers ----------------------------------------------------


def _line(p: QPainter, x1: float, y1: float, x2: float, y2: float) -> None:
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _rect(p: QPainter, x: float, y: float, w: float, h: float, r: float = 0) -> None:
    if r:
        p.drawRoundedRect(QRectF(x, y, w, h), r, r)
    else:
        p.drawRect(QRectF(x, y, w, h))


def _circle(p: QPainter, cx: float, cy: float, r: float) -> None:
    p.drawEllipse(QPointF(cx, cy), r, r)


def _polyline(p: QPainter, *points: tuple[float, float]) -> None:
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


# ----- individual drawers (canvas 24×24) ------------------------------------


def _grid(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _rect(p, o.x() + 3 * s, o.y() + 3 * s, 8 * s, 8 * s, 1.5 * s)
    _rect(p, o.x() + 13 * s, o.y() + 3 * s, 8 * s, 8 * s, 1.5 * s)
    _rect(p, o.x() + 3 * s, o.y() + 13 * s, 8 * s, 8 * s, 1.5 * s)
    _rect(p, o.x() + 13 * s, o.y() + 13 * s, 8 * s, 8 * s, 1.5 * s)


def _book(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _polyline(
        p,
        (o.x() + 4 * s, o.y() + 4 * s),
        (o.x() + 4 * s, o.y() + 20 * s),
        (o.x() + 18 * s, o.y() + 20 * s),
        (o.x() + 18 * s, o.y() + 4 * s),
        (o.x() + 4 * s, o.y() + 4 * s),
    )
    _line(p, o.x() + 8 * s, o.y() + 8 * s, o.x() + 14 * s, o.y() + 8 * s)
    _line(p, o.x() + 8 * s, o.y() + 12 * s, o.x() + 14 * s, o.y() + 12 * s)
    _line(p, o.x() + 8 * s, o.y() + 16 * s, o.x() + 12 * s, o.y() + 16 * s)


def _invoice(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _polyline(
        p,
        (o.x() + 6 * s, o.y() + 3 * s),
        (o.x() + 6 * s, o.y() + 21 * s),
        (o.x() + 9 * s, o.y() + 19 * s),
        (o.x() + 12 * s, o.y() + 21 * s),
        (o.x() + 15 * s, o.y() + 19 * s),
        (o.x() + 18 * s, o.y() + 21 * s),
        (o.x() + 18 * s, o.y() + 3 * s),
        (o.x() + 6 * s, o.y() + 3 * s),
    )
    _line(p, o.x() + 9 * s, o.y() + 8 * s, o.x() + 15 * s, o.y() + 8 * s)
    _line(p, o.x() + 9 * s, o.y() + 12 * s, o.x() + 15 * s, o.y() + 12 * s)


def _cart(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _polyline(
        p,
        (o.x() + 3 * s, o.y() + 5 * s),
        (o.x() + 6 * s, o.y() + 5 * s),
        (o.x() + 8 * s, o.y() + 16 * s),
        (o.x() + 19 * s, o.y() + 16 * s),
        (o.x() + 21 * s, o.y() + 8 * s),
        (o.x() + 7 * s, o.y() + 8 * s),
    )
    _circle(p, o.x() + 10 * s, o.y() + 20 * s, 1.2 * s)
    _circle(p, o.x() + 17 * s, o.y() + 20 * s, 1.2 * s)


def _box(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _polyline(
        p,
        (o.x() + 4 * s, o.y() + 8 * s),
        (o.x() + 12 * s, o.y() + 4 * s),
        (o.x() + 20 * s, o.y() + 8 * s),
        (o.x() + 20 * s, o.y() + 17 * s),
        (o.x() + 12 * s, o.y() + 21 * s),
        (o.x() + 4 * s, o.y() + 17 * s),
        (o.x() + 4 * s, o.y() + 8 * s),
    )
    _line(p, o.x() + 4 * s, o.y() + 8 * s, o.x() + 12 * s, o.y() + 12 * s)
    _line(p, o.x() + 12 * s, o.y() + 12 * s, o.x() + 20 * s, o.y() + 8 * s)
    _line(p, o.x() + 12 * s, o.y() + 12 * s, o.x() + 12 * s, o.y() + 21 * s)


def _wallet(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _rect(p, o.x() + 3 * s, o.y() + 6 * s, 18 * s, 13 * s, 2 * s)
    _circle(p, o.x() + 16 * s, o.y() + 12.5 * s, 1.2 * s)


def _cube(p: QPainter, r: QRectF) -> None:
    _box(p, r)


def _chart(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _line(p, o.x() + 4 * s, o.y() + 20 * s, o.x() + 20 * s, o.y() + 20 * s)
    _line(p, o.x() + 4 * s, o.y() + 4 * s, o.x() + 4 * s, o.y() + 20 * s)
    _polyline(
        p,
        (o.x() + 7 * s, o.y() + 16 * s),
        (o.x() + 11 * s, o.y() + 10 * s),
        (o.x() + 14 * s, o.y() + 13 * s),
        (o.x() + 19 * s, o.y() + 6 * s),
    )


def _tax(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _rect(p, o.x() + 5 * s, o.y() + 4 * s, 14 * s, 16 * s, 1.5 * s)
    _line(p, o.x() + 9 * s, o.y() + 9 * s, o.x() + 15 * s, o.y() + 15 * s)
    _circle(p, o.x() + 10 * s, o.y() + 10 * s, 1 * s)
    _circle(p, o.x() + 14 * s, o.y() + 14 * s, 1 * s)


def _search(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _circle(p, o.x() + 11 * s, o.y() + 11 * s, 6 * s)
    _line(p, o.x() + 15.5 * s, o.y() + 15.5 * s, o.x() + 20 * s, o.y() + 20 * s)


def _bell(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _polyline(
        p,
        (o.x() + 5 * s, o.y() + 17 * s),
        (o.x() + 19 * s, o.y() + 17 * s),
        (o.x() + 17 * s, o.y() + 14 * s),
        (o.x() + 17 * s, o.y() + 10 * s),
    )
    _polyline(
        p,
        (o.x() + 17 * s, o.y() + 10 * s),
        (o.x() + 12 * s, o.y() + 5 * s),
        (o.x() + 7 * s, o.y() + 10 * s),
        (o.x() + 7 * s, o.y() + 14 * s),
        (o.x() + 5 * s, o.y() + 17 * s),
    )
    _line(p, o.x() + 10 * s, o.y() + 20 * s, o.x() + 14 * s, o.y() + 20 * s)


def _plus(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _line(p, o.x() + 12 * s, o.y() + 5 * s, o.x() + 12 * s, o.y() + 19 * s)
    _line(p, o.x() + 5 * s, o.y() + 12 * s, o.x() + 19 * s, o.y() + 12 * s)


def _minus(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _line(p, o.x() + 5 * s, o.y() + 12 * s, o.x() + 19 * s, o.y() + 12 * s)


def _check(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _polyline(
        p,
        (o.x() + 5 * s, o.y() + 13 * s),
        (o.x() + 10 * s, o.y() + 18 * s),
        (o.x() + 19 * s, o.y() + 7 * s),
    )


def _x(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _line(p, o.x() + 6 * s, o.y() + 6 * s, o.x() + 18 * s, o.y() + 18 * s)
    _line(p, o.x() + 18 * s, o.y() + 6 * s, o.x() + 6 * s, o.y() + 18 * s)


def _filter(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _polyline(
        p,
        (o.x() + 4 * s, o.y() + 5 * s),
        (o.x() + 20 * s, o.y() + 5 * s),
        (o.x() + 14 * s, o.y() + 12 * s),
        (o.x() + 14 * s, o.y() + 19 * s),
        (o.x() + 10 * s, o.y() + 17 * s),
        (o.x() + 10 * s, o.y() + 12 * s),
        (o.x() + 4 * s, o.y() + 5 * s),
    )


def _download(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _line(p, o.x() + 12 * s, o.y() + 4 * s, o.x() + 12 * s, o.y() + 16 * s)
    _polyline(
        p,
        (o.x() + 7 * s, o.y() + 11 * s),
        (o.x() + 12 * s, o.y() + 16 * s),
        (o.x() + 17 * s, o.y() + 11 * s),
    )
    _line(p, o.x() + 5 * s, o.y() + 20 * s, o.x() + 19 * s, o.y() + 20 * s)


def _upload(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _line(p, o.x() + 12 * s, o.y() + 20 * s, o.x() + 12 * s, o.y() + 8 * s)
    _polyline(
        p,
        (o.x() + 7 * s, o.y() + 13 * s),
        (o.x() + 12 * s, o.y() + 8 * s),
        (o.x() + 17 * s, o.y() + 13 * s),
    )
    _line(p, o.x() + 5 * s, o.y() + 4 * s, o.x() + 19 * s, o.y() + 4 * s)


def _export(p: QPainter, r: QRectF) -> None:
    _upload(p, r)


def _print(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _rect(p, o.x() + 6 * s, o.y() + 4 * s, 12 * s, 6 * s)
    _rect(p, o.x() + 4 * s, o.y() + 10 * s, 16 * s, 8 * s, 1.5 * s)
    _rect(p, o.x() + 7 * s, o.y() + 14 * s, 10 * s, 6 * s)


def _settings(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _circle(p, o.x() + 12 * s, o.y() + 12 * s, 3 * s)
    _circle(p, o.x() + 12 * s, o.y() + 12 * s, 8 * s)


def _chevron_down(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _polyline(p, (o.x() + 6 * s, o.y() + 9 * s), (o.x() + 12 * s, o.y() + 15 * s), (o.x() + 18 * s, o.y() + 9 * s))


def _chevron_right(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _polyline(p, (o.x() + 9 * s, o.y() + 6 * s), (o.x() + 15 * s, o.y() + 12 * s), (o.x() + 9 * s, o.y() + 18 * s))


def _chevron_left(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _polyline(p, (o.x() + 15 * s, o.y() + 6 * s), (o.x() + 9 * s, o.y() + 12 * s), (o.x() + 15 * s, o.y() + 18 * s))


def _arrow_up(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _line(p, o.x() + 12 * s, o.y() + 5 * s, o.x() + 12 * s, o.y() + 19 * s)
    _polyline(p, (o.x() + 7 * s, o.y() + 10 * s), (o.x() + 12 * s, o.y() + 5 * s), (o.x() + 17 * s, o.y() + 10 * s))


def _arrow_down(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _line(p, o.x() + 12 * s, o.y() + 5 * s, o.x() + 12 * s, o.y() + 19 * s)
    _polyline(p, (o.x() + 7 * s, o.y() + 14 * s), (o.x() + 12 * s, o.y() + 19 * s), (o.x() + 17 * s, o.y() + 14 * s))


def _calendar(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _rect(p, o.x() + 4 * s, o.y() + 6 * s, 16 * s, 14 * s, 1.5 * s)
    _line(p, o.x() + 4 * s, o.y() + 11 * s, o.x() + 20 * s, o.y() + 11 * s)
    _line(p, o.x() + 9 * s, o.y() + 4 * s, o.x() + 9 * s, o.y() + 8 * s)
    _line(p, o.x() + 15 * s, o.y() + 4 * s, o.x() + 15 * s, o.y() + 8 * s)


def _edit(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _polyline(
        p,
        (o.x() + 4 * s, o.y() + 20 * s),
        (o.x() + 8 * s, o.y() + 20 * s),
        (o.x() + 19 * s, o.y() + 9 * s),
        (o.x() + 15 * s, o.y() + 5 * s),
        (o.x() + 4 * s, o.y() + 16 * s),
        (o.x() + 4 * s, o.y() + 20 * s),
    )


def _trash(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _rect(p, o.x() + 6 * s, o.y() + 7 * s, 12 * s, 13 * s, 1.5 * s)
    _line(p, o.x() + 4 * s, o.y() + 7 * s, o.x() + 20 * s, o.y() + 7 * s)
    _line(p, o.x() + 10 * s, o.y() + 4 * s, o.x() + 14 * s, o.y() + 4 * s)


def _dot(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    p.setBrush(p.pen().color())
    _circle(p, o.x() + 12 * s, o.y() + 12 * s, 3 * s)


def _building(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _rect(p, o.x() + 5 * s, o.y() + 4 * s, 14 * s, 16 * s)
    for row in range(3):
        y = 7 + row * 4
        _line(p, o.x() + 8 * s, o.y() + y * s, o.x() + 10 * s, o.y() + y * s)
        _line(p, o.x() + 14 * s, o.y() + y * s, o.x() + 16 * s, o.y() + y * s)


def _user(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _circle(p, o.x() + 12 * s, o.y() + 9 * s, 3.5 * s)
    _polyline(
        p,
        (o.x() + 5 * s, o.y() + 20 * s),
        (o.x() + 7 * s, o.y() + 15 * s),
        (o.x() + 17 * s, o.y() + 15 * s),
        (o.x() + 19 * s, o.y() + 20 * s),
    )


def _list_(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    for y in (7, 12, 17):
        _circle(p, o.x() + 6 * s, o.y() + y * s, 0.8 * s)
        _line(p, o.x() + 9 * s, o.y() + y * s, o.x() + 19 * s, o.y() + y * s)


def _menu(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    for y in (7, 12, 17):
        _line(p, o.x() + 5 * s, o.y() + y * s, o.x() + 19 * s, o.y() + y * s)


def _help(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _circle(p, o.x() + 12 * s, o.y() + 12 * s, 9 * s)
    _polyline(
        p,
        (o.x() + 9 * s, o.y() + 9.5 * s),
        (o.x() + 10 * s, o.y() + 8 * s),
        (o.x() + 12 * s, o.y() + 7.5 * s),
        (o.x() + 14 * s, o.y() + 8.5 * s),
        (o.x() + 14.5 * s, o.y() + 10.5 * s),
        (o.x() + 13 * s, o.y() + 12 * s),
        (o.x() + 12 * s, o.y() + 13 * s),
        (o.x() + 12 * s, o.y() + 14.5 * s),
    )
    _circle(p, o.x() + 12 * s, o.y() + 17 * s, 0.5 * s)


def _sparkle(p: QPainter, r: QRectF) -> None:
    s = r.width() / 24
    o = r.topLeft()
    _polyline(
        p,
        (o.x() + 12 * s, o.y() + 4 * s),
        (o.x() + 14 * s, o.y() + 10 * s),
        (o.x() + 20 * s, o.y() + 12 * s),
        (o.x() + 14 * s, o.y() + 14 * s),
        (o.x() + 12 * s, o.y() + 20 * s),
        (o.x() + 10 * s, o.y() + 14 * s),
        (o.x() + 4 * s, o.y() + 12 * s),
        (o.x() + 10 * s, o.y() + 10 * s),
        (o.x() + 12 * s, o.y() + 4 * s),
    )


_DRAWERS: dict[str, Drawer] = {
    "grid": _grid,
    "book": _book,
    "invoice": _invoice,
    "cart": _cart,
    "box": _box,
    "wallet": _wallet,
    "cube": _cube,
    "chart": _chart,
    "tax": _tax,
    "search": _search,
    "bell": _bell,
    "plus": _plus,
    "minus": _minus,
    "check": _check,
    "x": _x,
    "close": _x,
    "filter": _filter,
    "download": _download,
    "upload": _upload,
    "export": _export,
    "print": _print,
    "settings": _settings,
    "chevron-down": _chevron_down,
    "chevron-right": _chevron_right,
    "chevron-left": _chevron_left,
    "arrow-up": _arrow_up,
    "arrow-down": _arrow_down,
    "calendar": _calendar,
    "edit": _edit,
    "trash": _trash,
    "dot": _dot,
    "building": _building,
    "user": _user,
    "list": _list_,
    "menu": _menu,
    "help": _help,
    "sparkle": _sparkle,
    "min": _minus,
    "max": _box,
}


class _LineIconEngine(QIconEngine):
    """Renders an icon by calling the registered drawer with currentColor."""

    def __init__(self, drawer: Drawer, color: QColor, stroke: float) -> None:
        super().__init__()
        self._drawer = drawer
        self._color = color
        self._stroke = stroke

    def paint(self, painter: QPainter, rect: QRect, mode, state) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(self._color)
        pen.setWidthF(self._stroke)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        self._drawer(painter, QRectF(rect))
        painter.restore()

    def pixmap(self, size: QSize, mode, state) -> QPixmap:
        pix = QPixmap(size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        self.paint(painter, QRect(0, 0, size.width(), size.height()), mode, state)
        painter.end()
        return pix

    def clone(self) -> QIconEngine:
        return _LineIconEngine(self._drawer, self._color, self._stroke)


def icon(
    name: str,
    *,
    color: str | None = None,
    stroke: float = 1.5,
) -> QIcon:
    """Return a QIcon for the given semantic name.

    Falls back to a tiny dot if the name is unknown so missing icons stay
    visible during development.
    """
    drawer = _DRAWERS.get(name, _dot)
    fill = QColor(color or active_tokens().txt_2)
    return QIcon(_LineIconEngine(drawer, fill, stroke))


def available_icon_names() -> tuple[str, ...]:
    return tuple(sorted(_DRAWERS))
