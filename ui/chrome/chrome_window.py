"""Frameless main window: TitleBar · (Sidebar | TopBar + Content) · StatusBar."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QKeySequence, QMouseEvent, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import APP_NAME
from app.email_poller import EmailPoller
from app.period import active_period, set_active_period
from data.repositories.invoice_repo import InvoiceRepository
from domain.models.invoice import InvoiceKind, InvoiceStatus
from domain.services.closing_service import ClosingService
from ui.chrome.sidebar import Sidebar
from ui.modals.period_modal import PeriodModal
from ui.chrome.status_bar import StatusBar
from ui.chrome.title_bar import TitleBar
from ui.chrome.top_bar import TopBar
from ui.screens.assets_screen import AssetsScreen
from ui.screens.cash_screen import CashScreen
from ui.screens.dashboard_screen import DashboardScreen
from ui.screens.directory_screen import DirectoryScreen
from ui.screens.help_screen import HelpScreen
from ui.screens.inventory_screen import InventoryScreen
from ui.screens.journal_screen import JournalScreen
from ui.screens.purchase_screen import PurchaseScreen
from ui.screens.reports_screen import ReportsScreen
from ui.screens.sales_screen import SalesScreen
from ui.screens.settings_screen import SettingsScreen
from ui.screens.tax_screen import TaxScreen


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
    "help":       ("Hướng dẫn sử dụng",  "User Guide",                 "Hướng dẫn / Help"),
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
        self._title_bar.command.connect(self._handle_command)

        body = QWidget()
        body.setObjectName("Body")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.module_selected.connect(self._on_module_selected)
        self._sidebar.settings_requested.connect(
            lambda: self._on_module_selected("settings")
        )
        # Bind each module's function key straight from the sidebar's own table,
        # so the hint shown in the sidebar and the real shortcut can never drift.
        for key, _vi, _en, _icon, shortcut, _badge in Sidebar.MODULES:
            QShortcut(QKeySequence(shortcut), self,
                      activated=lambda k=key: self._on_module_selected(k))

        main_column = QWidget()
        main_column.setObjectName("MainColumn")
        col_layout = QVBoxLayout(main_column)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(0)

        self._top_bar = TopBar()
        self._top_bar.new_clicked.connect(self._new_journal_entry)
        self._top_bar.search_submitted.connect(self._global_search)
        self._top_bar.export_clicked.connect(lambda: self._on_module_selected("reports"))
        self._top_bar.print_clicked.connect(lambda: self._on_module_selected("reports"))
        self._top_bar.period_clicked.connect(self._show_period)
        self._top_bar.bell_clicked.connect(self._show_notifications)
        self._top_bar.user_clicked.connect(lambda: self._on_module_selected("settings"))

        self._stack = QStackedWidget()
        self._stack.setObjectName("ContentStack")
        self._screens: dict[str, QWidget] = {
            "dashboard": DashboardScreen(),
            "directory": DirectoryScreen(),
            "journal": JournalScreen(),
            "settings": SettingsScreen(),
            "sales": SalesScreen(),
            "inventory": InventoryScreen(),
            "purchase": PurchaseScreen(),
            "cash": CashScreen(),
            "assets": AssetsScreen(),
            "reports": ReportsScreen(),
            "tax": TaxScreen(),
            "help": HelpScreen(),
        }
        for screen in self._screens.values():
            self._stack.addWidget(screen)

        # Inventory can ask to jump to the Catalog when there are no items yet.
        self._screens["inventory"].navigate_requested.connect(self._on_module_selected)
        # User-guide "Mở …" links jump straight to the documented phân hệ.
        self._screens["help"].navigate_requested.connect(self._on_module_selected)

        col_layout.addWidget(self._top_bar)
        col_layout.addWidget(self._stack, 1)

        body_layout.addWidget(self._sidebar)
        body_layout.addWidget(main_column, 1)

        self._status_bar = StatusBar()

        root.addWidget(self._title_bar)
        root.addWidget(body, 1)
        root.addWidget(self._status_bar)

        self._status_bar.set_ledger(active_period().ledger_label)
        self._top_bar.set_period(active_period())

        self._on_module_selected("dashboard")
        self._sidebar.set_active("dashboard")

        self._check_year_closing()

        # Nền: tự lấy HĐĐT từ hộp thư nếu người dùng đã bật trong Cấu hình.
        self._email_poller = EmailPoller(self)
        self._email_poller.imported.connect(self._on_email_imported)
        self._email_poller.start()

    def _check_year_closing(self) -> None:
        """On launch: auto-close years overdue >48h and remind about pending ones."""
        closing = ClosingService()
        auto_closed = closing.auto_close_overdue()
        if auto_closed:
            years = ", ".join(str(y) for y in auto_closed)
            QMessageBox.information(
                self, "Tự động chốt sổ",
                f"Đã quá 48 giờ kể từ cuối năm mà chưa chốt sổ.\n"
                f"Hệ thống đã tự động chốt sổ năm: {years}.",
            )
        pending = closing.years_awaiting_close()
        if pending:
            years = ", ".join(str(y) for y in pending)
            QMessageBox.warning(
                self, "Nhắc chốt sổ",
                f"Năm {years} đã kết thúc nhưng chưa được chốt sổ.\n"
                "Vào Cấu hình › Chốt sổ cuối năm để chốt. Nếu không, hệ thống sẽ "
                "tự động chốt sau 48 giờ kể từ cuối năm.",
            )

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

        # Let a screen refresh itself from the live ledger each time it's shown.
        on_activated = getattr(screen, "on_activated", None)
        if callable(on_activated):
            on_activated()
        self._status_bar.mark_synced()
        self._refresh_sales_badge()

        meta = _SCREEN_META.get(key)
        if meta:
            vi, en, breadcrumb = meta
            self._top_bar.set_screen_title(vi, en)
            self._title_bar.set_breadcrumb(breadcrumb)

    def _refresh_sales_badge(self) -> None:
        """Badge the Sales module with the count of unposted (draft) invoices."""
        drafts = sum(
            1 for inv in InvoiceRepository().list_all(InvoiceKind.SALE)
            if inv.status is InvoiceStatus.DRAFT
        )
        self._sidebar.set_badge("sales", drafts)

    def _on_email_imported(self, result) -> None:
        """HĐĐT vừa được nền nhập về → làm tươi Bán/Mua hàng + badge + trạng thái."""
        for key in ("sales", "purchase"):
            screen = self._screens.get(key)
            on_activated = getattr(screen, "on_activated", None)
            if callable(on_activated):
                on_activated()
        self._refresh_sales_badge()
        self._status_bar.mark_synced()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        poller = getattr(self, "_email_poller", None)
        if poller is not None:
            poller.stop()
        super().closeEvent(event)

    # ----- title-bar / top-bar commands ------------------------------------

    def _handle_command(self, cmd: str) -> None:
        if cmd.startswith("go:"):
            self._on_module_selected(cmd[3:])
        elif cmd == "new":
            self._new_journal_entry()
        elif cmd == "search":
            self._top_bar.search_input().line_edit().setFocus()
        elif cmd == "close":
            self.close()
        elif cmd == "shortcuts":
            self._show_shortcuts()
        elif cmd == "about":
            self._show_about()

    def _new_journal_entry(self) -> None:
        self._on_module_selected("journal")
        journal = self._screens.get("journal")
        if journal is not None:
            journal._on_entry_new()
        self._refresh_sales_badge()

    def _global_search(self, text: str) -> None:
        query = text.strip()
        if not query:
            return
        self._on_module_selected("journal")
        journal = self._screens.get("journal")
        if journal is not None:
            journal._search.set_text(query)

    def _show_period(self) -> None:
        dialog = PeriodModal(self, current=active_period())
        if not dialog.exec():
            return
        period = dialog.period()
        set_active_period(period)
        self._top_bar.set_period(period)
        self._status_bar.set_ledger(period.ledger_label)
        # Re-filter whatever screen is showing against the new period.
        current = self._stack.currentWidget()
        on_activated = getattr(current, "on_activated", None)
        if callable(on_activated):
            on_activated()

    def _show_notifications(self) -> None:
        sales = InvoiceRepository().list_all(InvoiceKind.SALE)
        drafts = sum(1 for i in sales if i.status is InvoiceStatus.DRAFT)
        QMessageBox.information(
            self, "Thông báo",
            f"• {drafts} đơn hàng chưa ghi sổ đang chờ xử lý.\n"
            f"• Kỳ kế toán: {active_period().label}.\n"
            "• Nhớ lập tờ khai thuế GTGT cuối kỳ.",
        )

    def _show_shortcuts(self) -> None:
        QMessageBox.information(
            self, "Phím tắt",
            "F2–F10: chuyển phân hệ\n"
            "Ctrl+N: Bút toán mới\n"
            "Ctrl+I: Hóa đơn GTGT\n"
            "Ctrl+K: Tìm kiếm\n"
            "Ctrl+S: Lưu / Ghi sổ\n"
            "Esc: Đóng hộp thoại",
        )

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "Giới thiệu",
            "<b>Hưng Phát · Accounting Suite</b><br>"
            "Phần mềm kế toán theo Thông tư 200/133-BTC.<br><br>"
            "© Hưng Phát M&E · v3.2.0-py",
        )

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
