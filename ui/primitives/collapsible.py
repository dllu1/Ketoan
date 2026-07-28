"""CollapsibleSection: một khối nội dung thu gọn / mở ra được (dạng "drop down").

Header là một nút bấm có mũi tên ▸/▾ + tiêu đề (kiểu SectionLabel) và phần tóm
tắt tùy chọn bên phải (vd "· 2 dòng"). Bấm header để ẩn/hiện nội dung, giúp các
hộp thoại nhiều bảng (mua hàng: hàng hóa + chi phí dịch vụ) gọn gàng hơn.

Thêm nội dung qua :meth:`add_widget` / :meth:`add_layout`, hoặc lấy thẳng
:meth:`content_layout` (một QVBoxLayout).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class CollapsibleSection(QWidget):
    toggled = Signal(bool)

    def __init__(
        self, title: str, *, expanded: bool = True, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CollapsibleSection")
        self._title = title
        self._summary = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._header = QToolButton()
        self._header.setObjectName("CollapsibleHeader")
        self._header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._header.setCheckable(True)
        self._header.setChecked(expanded)
        self._header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.setStyleSheet(
            "#CollapsibleHeader {"
            " border: none; background: transparent; padding: 2px 0;"
            " font-weight: 600; letter-spacing: .04em; }"
        )
        self._header.clicked.connect(self._on_toggle)
        root.addWidget(self._header)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(6)
        root.addWidget(self._content, 1)
        self._content.setVisible(expanded)
        self._refresh_header()

    # ----- nội dung --------------------------------------------------------

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self._content_layout.addWidget(widget, stretch)

    def add_layout(self, layout) -> None:
        self._content_layout.addLayout(layout)

    # ----- đóng / mở -------------------------------------------------------

    def _on_toggle(self, checked: bool) -> None:
        self._content.setVisible(checked)
        self._header.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.toggled.emit(checked)

    def set_expanded(self, expanded: bool) -> None:
        self._header.setChecked(expanded)
        self._on_toggle(expanded)

    def is_expanded(self) -> bool:
        return self._header.isChecked()

    def set_summary(self, summary: str) -> None:
        """Chữ tóm tắt cạnh tiêu đề (vd '· 2 dòng'); rỗng để bỏ."""
        self._summary = summary
        self._refresh_header()

    def _refresh_header(self) -> None:
        text = self._title if not self._summary else f"{self._title}   {self._summary}"
        self._header.setText(text)
