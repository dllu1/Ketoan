"""Custom title bar for the frameless Chrome window."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)


class TitleBar(QWidget):
    HEIGHT = 36

    minimize_clicked = Signal()
    maximize_clicked = Signal()
    close_clicked = Signal()

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(self.HEIGHT)
        self._drag_offset: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(8)

        self._title = QLabel(title)
        self._title.setObjectName("TitleBarTitle")
        self._title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout.addWidget(self._title)

        for label, slot, name in (
            ("—", self.minimize_clicked.emit, "MinButton"),
            ("□", self.maximize_clicked.emit, "MaxButton"),
            ("✕", self.close_clicked.emit, "CloseButton"),
        ):
            btn = QPushButton(label)
            btn.setObjectName(name)
            btn.setFixedSize(46, self.HEIGHT)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(slot)
            layout.addWidget(btn)

    def set_title(self, title: str) -> None:
        self._title.setText(title)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            window = self.window()
            self._drag_offset = (
                event.globalPosition().toPoint() - window.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is None or not (event.buttons() & Qt.LeftButton):
            return
        window = self.window()
        if window.isMaximized():
            return
        window.move(event.globalPosition().toPoint() - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.maximize_clicked.emit()
