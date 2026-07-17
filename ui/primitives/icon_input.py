"""Input wrapper with a leading icon and optional trailing Kbd hint."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QWidget,
)

from ui.icons import icon as make_icon
from ui.primitives.kbd import Kbd

# Độ trễ gõ phím trước khi phát search_changed (ms). Đủ ngắn để thấy tức thì,
# đủ dài để không nạp lại bảng/DB sau mỗi ký tự khi người dùng đang gõ nhanh.
_DEBOUNCE_MS = 180


class IconInput(QFrame):
    text_changed = Signal(str)          # phát ngay mỗi ký tự (validate trực tiếp)
    search_changed = Signal(str)        # phát sau khi ngừng gõ (nạp/lọc dữ liệu)
    returned = Signal()

    def __init__(
        self,
        *,
        placeholder: str = "",
        icon_name: str = "search",
        kbd_hint: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("IconInput")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        self._icon_label = QLabel()
        self._icon_label.setPixmap(make_icon(icon_name).pixmap(QSize(16, 16)))
        self._icon_label.setFixedSize(QSize(16, 28))
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setStyleSheet("background: transparent; border: none;")

        self._line = QLineEdit()
        self._line.setPlaceholderText(placeholder)
        self._line.textChanged.connect(self.text_changed.emit)
        self._line.returnPressed.connect(self.returned.emit)

        # Gom nhiều lần gõ liên tiếp thành một lần phát search_changed.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(
            lambda: self.search_changed.emit(self._line.text())
        )
        self._line.textChanged.connect(lambda _: self._debounce.start())
        # Enter → tìm ngay, không đợi debounce.
        self._line.returnPressed.connect(
            lambda: (self._debounce.stop(), self.search_changed.emit(self._line.text()))
        )

        layout.addWidget(self._icon_label)
        layout.addWidget(self._line, 1)

        if kbd_hint:
            layout.addWidget(Kbd(kbd_hint))

        self.setFixedHeight(30)

    def text(self) -> str:
        return self._line.text()

    def set_text(self, value: str) -> None:
        self._line.setText(value)

    def clear(self) -> None:
        self._line.clear()

    def line_edit(self) -> QLineEdit:
        return self._line

    def setFocus(self, reason: Qt.FocusReason = Qt.OtherFocusReason) -> None:  # type: ignore[override]
        self._line.setFocus(reason)
