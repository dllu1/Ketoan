"""Frameless main window: TitleBar · (Sidebar | TopBar + Content) · StatusBar."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import APP_NAME
from ui.chrome.sidebar import Sidebar
from ui.chrome.status_bar import StatusBar
from ui.chrome.title_bar import TitleBar
from ui.chrome.top_bar import TopBar
from ui.screens.dashboard_screen import DashboardScreen
from ui.screens.directory_screen import DirectoryScreen


# (key, vi, en, breadcrumb-here)
_SCREEN_META: dict[str, tuple[str, str, str]] = {
    "dashboard":  ("Tổng quan",          "Dashboard / Overview",       "Tổng quan / Dashboard"),
    "journal":    ("Sổ nhật ký chung",   "General Journal",            "Sổ nhật ký / Journal"),
    "sales":      ("Bán hàng",           "Sales",                      "Bán hàng / Sales"),
    "purchase":   ("Mua hàng",           "Purchases",                  "Mua hàng / Purchases"),
    "inventory":  ("Kho hàng",           "Inventory",                  "Kho hàng / Inventory"),
    "cash":       ("Quỹ & Ngân hàng",    "Cash & Bank",                "Quỹ & Ngân hàng / Cash"),
    "assets":     ("Tài sản cố định",    "Fixed Assets",               "TSCĐ / Fixed Assets"),
    "reports":    ("Báo cáo tài chính",  "Financial Reports",          "Báo cáo / Reports"),
    "tax":        ("Báo cáo thuế",       "Tax Reports",                "Báo cáo thuế / Tax"),
    "directory":  ("Danh mục",           "Catalog",                    "Danh mục / Catalog"),
    "settings":   ("Cấu hình",           "Settings",                   "Cấu hình / Settings"),
}


class ChromeWindow(QWidget):
    RESIZE_MARGIN = 6

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ChromeWindow")
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setMouseTracking(True)
        self.setMinimumSize(1100, 700)

        self._resize_edge = None
        self._resize_start_geo: QRect | None = None
        self._resize_start_pos: QPoint | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        self._title_bar = TitleBar()
        self._title_bar.minimize_clicked.connect(self.showMinimized)
        self._title_bar.maximize_clicked.connect(self._toggle_maximize)
        self._title_bar.close_clicked.connect(self.close)

        body = QWidget()
        body.setObjectName("Body")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.module_selected.connect(self._on_module_selected)

        main_column = QWidget()
        main_column.setObjectName("MainColumn")
        col_layout = QVBoxLayout(main_column)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(0)

        self._top_bar = TopBar()

        self._stack = QStackedWidget()
        self._stack.setObjectName("ContentStack")
        self._screens: dict[str, QWidget] = {
            "dashboard": DashboardScreen(),
            "directory": DirectoryScreen(),
        }
        for screen in self._screens.values():
            self._stack.addWidget(screen)

        col_layout.addWidget(self._top_bar)
        col_layout.addWidget(self._stack, 1)

        body_layout.addWidget(self._sidebar)
        body_layout.addWidget(main_column, 1)

        self._status_bar = StatusBar()

        root.addWidget(self._title_bar)
        root.addWidget(body, 1)
        root.addWidget(self._status_bar)

        self._on_module_selected("dashboard")
        self._sidebar.set_active("dashboard")

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _on_module_selected(self, key: str) -> None:
        screen = self._screens.get(key)
        if screen is None:
            placeholder = _Placeholder(key)
            self._screens[key] = placeholder
            self._stack.addWidget(placeholder)
            screen = placeholder
        self._stack.setCurrentWidget(screen)
        self._sidebar.set_active(key)

        meta = _SCREEN_META.get(key)
        if meta:
            vi, en, breadcrumb = meta
            self._top_bar.set_screen_title(vi, en)
            self._title_bar.set_breadcrumb(breadcrumb)

    # --- frameless resize handling -----------------------------------------

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._resize_edge and (event.buttons() & Qt.LeftButton):
            self._perform_resize(event.globalPosition().toPoint())
            return
        self._update_cursor(event.position().toPoint())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            edge = self._edge_at(event.position().toPoint())
            if edge:
                self._resize_edge = edge
                self._resize_start_geo = self.geometry()
                self._resize_start_pos = event.globalPosition().toPoint()
                event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._resize_edge = None
        self._resize_start_geo = None
        self._resize_start_pos = None
        self.unsetCursor()

    def _edge_at(self, pos: QPoint):
        if self.isMaximized():
            return None
        m = self.RESIZE_MARGIN
        rect = self.rect()
        edge = Qt.Edges()
        if pos.x() <= m:
            edge |= Qt.LeftEdge
        elif pos.x() >= rect.width() - m:
            edge |= Qt.RightEdge
        if pos.y() <= m:
            edge |= Qt.TopEdge
        elif pos.y() >= rect.height() - m:
            edge |= Qt.BottomEdge
        return edge if edge else None

    def _update_cursor(self, pos: QPoint) -> None:
        edge = self._edge_at(pos)
        if edge is None:
            self.unsetCursor()
            return
        top = bool(edge & Qt.TopEdge)
        bottom = bool(edge & Qt.BottomEdge)
        left = bool(edge & Qt.LeftEdge)
        right = bool(edge & Qt.RightEdge)
        if (top and left) or (bottom and right):
            self.setCursor(Qt.SizeFDiagCursor)
        elif (top and right) or (bottom and left):
            self.setCursor(Qt.SizeBDiagCursor)
        elif left or right:
            self.setCursor(Qt.SizeHorCursor)
        elif top or bottom:
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.unsetCursor()

    def _perform_resize(self, global_pos: QPoint) -> None:
        if not (self._resize_edge and self._resize_start_geo and self._resize_start_pos):
            return
        delta = global_pos - self._resize_start_pos
        geo = QRect(self._resize_start_geo)
        min_w = self.minimumWidth()
        min_h = self.minimumHeight()
        if self._resize_edge & Qt.LeftEdge:
            new_x = geo.x() + delta.x()
            new_w = geo.width() - delta.x()
            if new_w >= min_w:
                geo.setX(new_x)
                geo.setWidth(new_w)
        if self._resize_edge & Qt.RightEdge:
            geo.setWidth(max(min_w, geo.width() + delta.x()))
        if self._resize_edge & Qt.TopEdge:
            new_y = geo.y() + delta.y()
            new_h = geo.height() - delta.y()
            if new_h >= min_h:
                geo.setY(new_y)
                geo.setHeight(new_h)
        if self._resize_edge & Qt.BottomEdge:
            geo.setHeight(max(min_h, geo.height() + delta.y()))
        self.setGeometry(geo)


class _Placeholder(QWidget):
    def __init__(self, key: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel(f"Module '{key}' — sẽ được triển khai ở phase sau")
        label.setObjectName("PlaceholderLabel")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
