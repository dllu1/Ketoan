"""232px Sidebar matching components/nav.jsx — head · search · modules · footer."""
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

from ui.primitives.icon_input import IconInput
from ui.icons import icon as make_icon


class _SidebarItem(QPushButton):
    """A module row: icon · (VI label / EN label) · (badge?) · shortcut."""

    def __init__(
        self,
        key: str,
        vi: str,
        en: str,
        icon_name: str,
        shortcut: str,
        *,
        badge: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.key = key
        self.setObjectName("SidebarItem")
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(40)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(10)

        icon_label = QLabel()
        icon_label.setPixmap(make_icon(icon_name, color="#7e8da3").pixmap(QSize(16, 16)))
        icon_label.setFixedSize(QSize(18, 18))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border: none;")

        labels = QVBoxLayout()
        labels.setContentsMargins(0, 0, 0, 0)
        labels.setSpacing(0)
        vi_label = QLabel(vi)
        vi_label.setObjectName("SidebarItemVi")
        en_label = QLabel(en.upper())
        en_label.setObjectName("SidebarItemEn")
        labels.addWidget(vi_label)
        labels.addWidget(en_label)

        row.addWidget(icon_label)
        row.addLayout(labels, 1)

        if badge is not None:
            badge_label = QLabel(str(badge))
            badge_label.setObjectName("SidebarItemBadge")
            badge_label.setAlignment(Qt.AlignCenter)
            row.addWidget(badge_label)

        shortcut_label = QLabel(shortcut)
        shortcut_label.setObjectName("SidebarItemHot")
        row.addWidget(shortcut_label)


class Sidebar(QFrame):
    WIDTH = 232

    module_selected = Signal(str)
    search_submitted = Signal(str)
    settings_requested = Signal()

    # key, vi, en, icon, shortcut, badge
    MODULES: tuple[tuple[str, str, str, str, str, int | None], ...] = (
        ("dashboard", "Tổng quan",        "Dashboard",         "grid",    "F2",  None),
        ("journal",   "Sổ nhật ký chung", "General Journal",   "book",    "F3",  None),
        ("sales",     "Bán hàng",         "Sales",             "invoice", "F4",  7),
        ("purchase",  "Mua hàng",         "Purchases",         "cart",    "F5",  None),
        ("inventory", "Kho hàng",         "Inventory",         "box",     "F6",  None),
        ("cash",      "Quỹ & Ngân hàng",  "Cash & Bank",       "wallet",  "F7",  None),
        ("assets",    "Tài sản cố định",  "Fixed Assets",      "cube",    "F8",  None),
        ("reports",   "Báo cáo tài chính","Financial Reports", "chart",   "F9",  None),
        ("tax",       "Báo cáo thuế",     "Tax Reports",       "tax",     "F10", None),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(self.WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_head())
        root.addWidget(self._build_search())
        root.addWidget(self._build_section_label())
        root.addLayout(self._build_nav())
        root.addStretch(1)
        root.addWidget(self._build_footer())

    # ---- builders ---------------------------------------------------------

    def _build_head(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("SidebarHead")
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        crest = QLabel("HP")
        crest.setObjectName("SidebarCrest")
        crest.setFixedSize(QSize(32, 32))
        crest.setAlignment(Qt.AlignCenter)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        name = QLabel("Hưng Phát M&E")
        name.setObjectName("SidebarCompanyName")
        meta = QLabel("MST · 0312-654-987")
        meta.setObjectName("SidebarCompanyMeta")
        col.addWidget(name)
        col.addWidget(meta)

        layout.addWidget(crest)
        layout.addLayout(col, 1)
        return wrap

    def _build_search(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(14, 10, 14, 6)
        self._search = IconInput(
            placeholder="Tìm theo TK, KH, phiếu…",
            icon_name="search",
            kbd_hint="Ctrl K",
        )
        self._search.returned.connect(
            lambda: self.search_submitted.emit(self._search.text())
        )
        layout.addWidget(self._search)
        return wrap

    def _build_section_label(self) -> QWidget:
        wrap = QWidget()
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(14, 6, 14, 4)
        label = QLabel("PHÂN HỆ / MODULES")
        label.setObjectName("SidebarSectionLabel")
        layout.addWidget(label)
        layout.addStretch(1)
        return wrap

    def _build_nav(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(2)

        self._buttons: dict[str, _SidebarItem] = {}
        for key, vi, en, icon_name, shortcut, badge in self.MODULES:
            btn = _SidebarItem(key, vi, en, icon_name, shortcut, badge=badge)
            btn.clicked.connect(lambda _=False, k=key: self.module_selected.emit(k))
            layout.addWidget(btn)
            self._buttons[key] = btn
        return layout

    def _build_footer(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("SidebarFoot")
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        avatar = QLabel("NMA")
        avatar.setObjectName("SidebarFootAvatar")
        avatar.setFixedSize(QSize(28, 28))
        avatar.setAlignment(Qt.AlignCenter)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        name = QLabel("Nguyễn Mai Anh")
        name.setObjectName("SidebarFootName")
        role = QLabel("Kế toán trưởng")
        role.setObjectName("SidebarFootRole")
        col.addWidget(name)
        col.addWidget(role)

        gear = QPushButton()
        gear.setObjectName("SidebarFootGear")
        gear.setIcon(make_icon("settings"))
        gear.setIconSize(QSize(14, 14))
        gear.setFixedSize(QSize(24, 24))
        gear.setCursor(Qt.PointingHandCursor)
        gear.clicked.connect(self.settings_requested.emit)

        layout.addWidget(avatar)
        layout.addLayout(col, 1)
        layout.addWidget(gear)
        return wrap

    # ---- API --------------------------------------------------------------

    def set_active(self, module_key: str) -> None:
        btn = self._buttons.get(module_key)
        if btn:
            btn.setChecked(True)

    def search_input(self) -> IconInput:
        return self._search
