"""32px title bar matching components/chrome.jsx — brand · menus · breadcrumb · controls."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ui.icons import icon as make_icon


class TitleBar(QFrame):
    HEIGHT = 32

    minimize_clicked = Signal()
    maximize_clicked = Signal()
    close_clicked = Signal()
    menu_opened = Signal(str)

    MENUS: tuple[str, ...] = (
        "Tệp / File",
        "Hệ thống",
        "Danh mục",
        "Nghiệp vụ",
        "Báo cáo",
        "Tiện ích",
        "Trợ giúp",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._drag_offset: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(self._build_brand_block())
        layout.addWidget(self._build_menu_block())
        layout.addWidget(self._build_breadcrumb(), 1)
        layout.addSpacing(8)
        layout.addWidget(self._build_controls())

    # ---- blocks -----------------------------------------------------------

    def _build_brand_block(self) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet(
            "QFrame { border-right: 1px solid #1c2538; background: transparent; }"
        )
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        crest = QLabel("HP")
        crest.setObjectName("TitleBrandCrest")
        crest.setFixedSize(QSize(18, 18))
        crest.setAlignment(Qt.AlignCenter)

        brand_text = QLabel("HUNG PHAT · ACCOUNTING SUITE")
        brand_text.setObjectName("TitleBrandText")

        version = QLabel("v3.2.0-py")
        version.setObjectName("TitleBrandVersion")

        layout.addWidget(crest)
        layout.addWidget(brand_text)
        layout.addWidget(version)
        return wrap

    def _build_menu_block(self) -> QWidget:
        wrap = QWidget()
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        for name in self.MENUS:
            btn = QPushButton(name)
            btn.setObjectName("TitleMenu")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFlat(True)
            btn.setMinimumHeight(self.HEIGHT)
            btn.clicked.connect(lambda _=False, n=name: self.menu_opened.emit(n))
            layout.addWidget(btn)
        return wrap

    def _build_breadcrumb(self) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet("QFrame { background: transparent; }")
        # Let the breadcrumb shrink so it never crowds the menu block.
        wrap.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        chev = QLabel()
        chev.setPixmap(make_icon("chevron-right", color="#7e8da3").pixmap(QSize(12, 12)))
        chev.setStyleSheet("background: transparent; border: none;")

        self._breadcrumb_here = QLabel("Tổng quan / Dashboard")
        self._breadcrumb_here.setObjectName("TitleBreadcrumbHere")

        sep1 = QLabel("·")
        sep1.setObjectName("TitleBreadcrumbSep")

        self._breadcrumb_period = QLabel("Kỳ 01/2026")
        self._breadcrumb_period.setObjectName("TitleBreadcrumbMuted")

        layout.addStretch(1)
        layout.addWidget(chev)
        layout.addWidget(self._breadcrumb_here)
        layout.addWidget(sep1)
        layout.addWidget(self._breadcrumb_period)
        return wrap

    def _build_controls(self) -> QWidget:
        wrap = QWidget()
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        for icon_name, slot, obj in (
            ("min", self.minimize_clicked.emit, "MinButton"),
            ("max", self.maximize_clicked.emit, "MaxButton"),
            ("close", self.close_clicked.emit, "CloseButton"),
        ):
            btn = QPushButton()
            btn.setObjectName(obj)
            btn.setIcon(make_icon(icon_name, color="#b6c2d2"))
            btn.setIconSize(QSize(10, 10))
            btn.setFixedSize(46, self.HEIGHT)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(slot)
            layout.addWidget(btn)
        return wrap

    # ---- API --------------------------------------------------------------

    def set_breadcrumb(self, here: str, period: str | None = None, company: str | None = None) -> None:
        self._breadcrumb_here.setText(here)
        if period:
            self._breadcrumb_period.setText(period)
        if company:
            self._breadcrumb_company.setText(company)

    # ---- drag-to-move -----------------------------------------------------

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
