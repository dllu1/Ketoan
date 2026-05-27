"""54px secondary top bar — title · search · period · primary action · icons · user."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.icons import icon as make_icon
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.icon_input import IconInput
from ui.primitives.kbd import Kbd


class TopBar(QFrame):
    HEIGHT = 54

    new_clicked = Signal()
    search_submitted = Signal(str)
    period_clicked = Signal()
    bell_clicked = Signal()
    user_clicked = Signal()
    export_clicked = Signal()
    print_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_title())
        layout.addWidget(self._build_search(), 1)
        layout.addWidget(self._build_period())
        layout.addWidget(self._build_primary())
        layout.addWidget(self._build_icon_button("export", self.export_clicked.emit, "Xuất Excel"))
        layout.addWidget(self._build_icon_button("print", self.print_clicked.emit, "In"))
        layout.addWidget(self._build_icon_button("grid", lambda: None, "Components Library"))
        layout.addWidget(self._build_bell())
        layout.addWidget(self._build_user())

    # ---- builders ---------------------------------------------------------

    def _build_title(self) -> QWidget:
        wrap = QWidget()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(0, 0, 6, 0)
        col.setSpacing(0)

        self._title_vi = QLabel("Tổng quan")
        self._title_vi.setObjectName("TopBarTitleVi")
        self._title_en = QLabel("DASHBOARD / OVERVIEW")
        self._title_en.setObjectName("TopBarTitleEn")
        col.addWidget(self._title_vi)
        col.addWidget(self._title_en)
        return wrap

    def _build_search(self) -> QWidget:
        self._search = IconInput(
            placeholder="Tìm bút toán, hóa đơn, khách hàng, mã hàng…",
            icon_name="search",
            kbd_hint="Ctrl K",
        )
        self._search.setMaximumWidth(520)
        self._search.returned.connect(
            lambda: self.search_submitted.emit(self._search.text())
        )
        return self._search

    def _build_period(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("TopBarPeriod")
        wrap.setCursor(Qt.PointingHandCursor)
        wrap.setFixedHeight(36)
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(14, 0, 12, 0)
        layout.setSpacing(10)

        cal = QLabel()
        cal.setPixmap(make_icon("calendar", color="#7e8da3").pixmap(QSize(14, 14)))
        cal.setStyleSheet("background: transparent; border: none;")

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)
        lab = QLabel("KỲ KẾ TOÁN")
        lab.setObjectName("TopBarPeriodLabel")
        val = QLabel("01 / 2026")
        val.setObjectName("TopBarPeriodValue")
        col.addWidget(lab)
        col.addWidget(val)

        chev = QLabel()
        chev.setPixmap(make_icon("chevron-down", color="#7e8da3").pixmap(QSize(12, 12)))
        chev.setStyleSheet("background: transparent; border: none;")

        layout.addWidget(cal)
        layout.addLayout(col)
        layout.addWidget(chev)

        wrap.mousePressEvent = lambda _e: self.period_clicked.emit()  # type: ignore[assignment]
        return wrap

    def _build_primary(self) -> QWidget:
        btn = Button("Bút toán mới", variant=ButtonVariant.PRIMARY, icon_name="plus")
        btn.setMinimumHeight(36)
        btn.setMinimumWidth(160)
        # append kbd hint visually inside the button is non-trivial in Qt;
        # use tooltip and a sibling Kbd outside instead.
        btn.setToolTip("Tạo bút toán mới  ·  Ctrl+N")
        btn.clicked.connect(self.new_clicked.emit)
        return btn

    def _build_icon_button(self, icon_name: str, slot, tooltip: str) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("TopBarIconButton")
        btn.setIcon(make_icon(icon_name))
        btn.setIconSize(QSize(16, 16))
        btn.setFixedSize(QSize(32, 32))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tooltip)
        btn.clicked.connect(slot)
        return btn

    def _build_bell(self) -> QWidget:
        wrap = QWidget()
        wrap.setFixedSize(QSize(32, 32))
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        btn = self._build_icon_button("bell", self.bell_clicked.emit, "Thông báo")
        layout.addWidget(btn)

        pin = QLabel("5", btn)
        pin.setObjectName("TopBarNotificationPin")
        pin.setAlignment(Qt.AlignCenter)
        pin.adjustSize()
        pin.setMinimumSize(QSize(14, 14))
        pin.move(btn.width() - pin.width() - 2, 2)
        return wrap

    def _build_user(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("TopBarUser")
        wrap.setCursor(Qt.PointingHandCursor)
        wrap.setFixedHeight(36)
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(10)

        av = QLabel("NMA")
        av.setObjectName("TopBarUserAvatar")
        av.setFixedSize(QSize(24, 24))
        av.setAlignment(Qt.AlignCenter)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        name = QLabel("N.M.Anh")
        name.setObjectName("TopBarUserName")
        role = QLabel("Kế toán trưởng")
        role.setObjectName("TopBarUserRole")
        col.addWidget(name)
        col.addWidget(role)

        chev = QLabel()
        chev.setPixmap(make_icon("chevron-down", color="#7e8da3").pixmap(QSize(12, 12)))
        chev.setStyleSheet("background: transparent; border: none;")

        layout.addWidget(av)
        layout.addLayout(col)
        layout.addWidget(chev)

        wrap.mousePressEvent = lambda _e: self.user_clicked.emit()  # type: ignore[assignment]
        return wrap

    # ---- API --------------------------------------------------------------

    def set_screen_title(self, vi: str, en: str) -> None:
        self._title_vi.setText(vi)
        self._title_en.setText(en.upper())
