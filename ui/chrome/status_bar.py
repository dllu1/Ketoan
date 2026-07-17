"""24px status bar with brand background — all styles in QSS."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ui.icons import icon as make_icon
from ui.tokens import active_tokens


class StatusBar(QWidget):
    HEIGHT = 24

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setFixedHeight(self.HEIGHT)
        self._build()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(active_tokens().brand))
        painter.end()

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(12)

        online_pill = QLabel("● ONLINE")
        online_pill.setObjectName("StatusBarPill")
        online_pill.setAlignment(Qt.AlignCenter)
        layout.addWidget(online_pill)

        self._ledger = QLabel("Số cái: 01.01.2026 → 31.12.2026")
        self._ledger.setObjectName("StatusBarText")
        layout.addWidget(self._ledger)

        layout.addWidget(self._sep())
        self._sync = QLabel()
        layout.addWidget(self._icon_text("download", "", value_label=self._sync))
        self.mark_synced()

        layout.addStretch(1)

        layout.addWidget(self._kbd_text("F1", "Help"))
        layout.addWidget(self._kbd_text("Ctrl N", "Bút toán"))
        layout.addWidget(self._kbd_text("Ctrl K", "Tìm"))
        layout.addWidget(self._sep())

        self._user = QLabel("LMN · KT")
        self._user.setObjectName("StatusBarPill")
        self._user.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._user)

        version = QLabel("v3.2.0")
        version.setObjectName("StatusBarText")
        layout.addWidget(version)

    # ---- helpers ----------------------------------------------------------

    @staticmethod
    def _sep() -> QLabel:
        sep = QLabel("·")
        sep.setObjectName("StatusBarSep")
        return sep

    def _icon_text(
        self, icon_name: str, text: str, value_label: QLabel | None = None
    ) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("StatusBarItem")
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        ic = QLabel()
        ic.setObjectName("StatusBarIcon")
        ic.setPixmap(make_icon(icon_name, color="#0a1220").pixmap(QSize(10, 10)))
        layout.addWidget(ic)

        text_label = value_label if value_label is not None else QLabel(text)
        text_label.setObjectName("StatusBarText")
        layout.addWidget(text_label)
        return wrap

    @staticmethod
    def _kbd_text(key: str, label: str) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("StatusBarItem")
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        k = QLabel(key)
        k.setObjectName("StatusBarKbd")
        k.setAlignment(Qt.AlignCenter)
        layout.addWidget(k)

        t = QLabel(label)
        t.setObjectName("StatusBarText")
        layout.addWidget(t)
        return wrap

    # ---- API --------------------------------------------------------------

    def set_ledger(self, text: str) -> None:
        self._ledger.setText(text)

    def set_user(self, text: str) -> None:
        self._user.setText(text)

    def set_sync_time(self, moment: datetime) -> None:
        self._sync.setText(f"Đồng bộ {moment.strftime('%H:%M')}")

    def mark_synced(self) -> None:
        """Record that the live ledger was just (re)loaded into the UI."""
        self.set_sync_time(datetime.now())
