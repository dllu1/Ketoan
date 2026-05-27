"""Bottom status bar: connection / user / active ledger."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class StatusBar(QWidget):
    HEIGHT = 24

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setFixedHeight(self.HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(16)

        self._connection = QLabel("● SQLite local")
        self._connection.setObjectName("StatusConnection")
        self._user = QLabel("Người dùng: admin")
        self._ledger = QLabel("Kỳ kế toán: 2026")

        layout.addWidget(self._connection)
        layout.addWidget(self._user)
        layout.addStretch(1)
        layout.addWidget(self._ledger, alignment=Qt.AlignRight)

    def set_connection(self, text: str) -> None:
        self._connection.setText(text)

    def set_user(self, text: str) -> None:
        self._user.setText(text)

    def set_ledger(self, text: str) -> None:
        self._ledger.setText(text)
