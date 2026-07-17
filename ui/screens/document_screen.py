"""DocumentScreen: shared list/detail + posting workflow for sales & purchases."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.period import active_period
from domain.models.invoice import Invoice, InvoiceKind, InvoiceStatus
from domain.money import format_money
from domain.services.document_service import DocumentService
from ui.modals.invoice_modal import InvoiceModal
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.icon_input import IconInput

_STATUS_LABELS = {InvoiceStatus.DRAFT: "Nháp", InvoiceStatus.POSTED: "Đã ghi sổ"}
_CANCELLED = object()


@dataclass(frozen=True)
class DocumentScreenConfig:
    kind: InvoiceKind
    title: str
    search_placeholder: str
    new_label: str
    new_icon: str
    partner_header: str        # cột "Khách hàng" / "Nhà cung cấp"
    partner_noun: str          # "khách hàng" / "nhà cung cấp" (dùng trong câu hỏi lưu)
    shortcut: str | None = None


class DocumentScreen(QWidget):
    def __init__(self, service: DocumentService, config: DocumentScreenConfig) -> None:
        super().__init__()
        self.setObjectName("DocumentScreen")
        self._service = service
        self._cfg = config

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel(config.title)
        title.setObjectName("ScreenTitle")
        root.addWidget(title)

        toolbar = QHBoxLayout()
        self._search = IconInput(placeholder=config.search_placeholder, icon_name="search")
        self._search.search_changed.connect(lambda _: self._reload())

        btn_new = Button(config.new_label, variant=ButtonVariant.PRIMARY, icon_name=config.new_icon)
        btn_new.clicked.connect(self._on_new)
        btn_edit = Button("Sửa", icon_name="edit")
        btn_edit.clicked.connect(self._on_edit)
        self._btn_post = Button("Ghi sổ", icon_name="check")
        self._btn_post.clicked.connect(self._on_post)
        btn_delete = Button("Xóa", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_delete.clicked.connect(self._on_delete)
        btn_email = Button("Lấy từ email", icon_name="invoice")
        btn_email.clicked.connect(self._on_fetch_email)

        toolbar.addWidget(self._search, 1)
        toolbar.addWidget(btn_email)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(self._btn_post)
        toolbar.addWidget(btn_delete)
        toolbar.addWidget(btn_new)
        root.addLayout(toolbar)

        # Báo đỏ: chứng từ có đối tác chưa có trong danh mục (ẩn khi không có).
        self._partner_banner = QFrame()
        self._partner_banner.setObjectName("PartnerAlertBanner")
        self._partner_banner.setStyleSheet(
            "#PartnerAlertBanner {"
            " background: #fdecea; border: 1px solid #e74c3c; border-radius: 6px; }"
            "#PartnerAlertBanner QLabel { color: #c0392b; background: transparent;"
            " border: none; }"
        )
        banner_row = QHBoxLayout(self._partner_banner)
        banner_row.setContentsMargins(12, 8, 12, 8)
        banner_row.setSpacing(10)
        self._banner_label = QLabel("")
        banner_row.addWidget(self._banner_label, 1)
        btn_save_partner = Button(
            f"Lưu {config.partner_noun} vào danh mục",
            variant=ButtonVariant.DANGER, icon_name="check",
        )
        btn_save_partner.clicked.connect(self._on_save_unknown_partner)
        banner_row.addWidget(btn_save_partner)
        self._partner_banner.hide()
        root.addWidget(self._partner_banner)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Ngày", "Số CT", config.partner_header, "Tổng tiền", "TT", "Trạng thái"]
        )
        self._configure_table(self._table)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.currentCellChanged.connect(lambda *_: self._show_lines())
        self._table.itemDoubleClicked.connect(lambda *_: self._on_edit())
        root.addWidget(self._table, 3)

        lines_label = QLabel("Dòng hàng")
        lines_label.setObjectName("SectionLabel")
        root.addWidget(lines_label)

        self._line_table = QTableWidget(0, 7)
        self._line_table.setHorizontalHeaderLabels(
            ["Mã hàng", "Tên hàng", "ĐVT", "Mã kho", "SL", "Đơn giá", "Thành tiền"]
        )
        self._configure_table(self._line_table)
        self._line_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        root.addWidget(self._line_table, 2)

        if config.shortcut:
            QShortcut(QKeySequence(config.shortcut), self, activated=self._on_new)

        self._reload()

    # ----- list/detail --------------------------------------------------

    def on_activated(self) -> None:
        """Refresh from the ledger each time the tab is shown.

        Picks up invoices filed from elsewhere (vd: kèm theo bút toán ở Sổ nhật
        ký chung) without the user having to trigger a search.
        """
        self._reload()

    def _reload(self) -> None:
        query = self._search.text() if hasattr(self, "_search") else ""
        period = active_period()
        invoices = [
            inv for inv in self._service.search(query)
            if period.matches(inv.invoice_date)
        ]
        self._table.setRowCount(0)
        unknown_count = 0
        for inv in invoices:
            row = self._table.rowCount()
            self._table.insertRow(row)
            is_unknown = self._service.partner_is_unknown(inv)
            if is_unknown:
                unknown_count += 1
            partner = inv.partner_name or inv.partner_code or "—"
            if is_unknown:
                partner += "  • chưa có trong DM"
            cells = [
                inv.invoice_date.strftime("%d/%m/%Y"),
                inv.ref,
                partner,
                format_money(inv.grand_total),
                inv.payment_method.value,
                _STATUS_LABELS.get(inv.status, inv.status.value),
            ]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.UserRole, inv.id)
                if col == 3:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                # Báo đỏ: tô đỏ cột đối tác + trạng thái của chứng từ đối tác lạ.
                if is_unknown and col in (2, 5):
                    item.setForeground(QColor("#c0392b"))
                self._table.setItem(row, col, item)
        self._update_partner_banner(unknown_count)
        self._show_lines()

    def _update_partner_banner(self, unknown_count: int) -> None:
        if unknown_count <= 0:
            self._partner_banner.hide()
            return
        self._banner_label.setText(
            f"⚠ {unknown_count} chứng từ có {self._cfg.partner_noun} chưa có trong "
            f"danh mục. Chọn chứng từ rồi bấm để lưu vào danh mục "
            f"{self._cfg.partner_noun}."
        )
        self._partner_banner.show()

    def _show_lines(self) -> None:
        invoice = self._selected()
        self._line_table.setRowCount(0)
        if invoice is None:
            return
        for line in invoice.lines:
            row = self._line_table.rowCount()
            self._line_table.insertRow(row)
            cells = [
                line.item_code,
                line.item_name,
                line.unit,
                line.account_code,
                f"{line.quantity:g}",
                format_money(line.unit_price),
                format_money(line.amount),
            ]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col in (4, 5, 6):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._line_table.setItem(row, col, item)

    # ----- actions ------------------------------------------------------

    def _on_new(self) -> None:
        dialog = InvoiceModal(self, kind=self._cfg.kind)
        if not dialog.exec():
            return
        self._save(
            dialog.invoice(), is_update=False,
            partner_decision=dialog.wants_save_partner(),
        )

    def _on_edit(self) -> None:
        invoice = self._selected()
        if invoice is None:
            return
        # Posted documents stay editable all year now; only a closed fiscal
        # year (chốt sổ) blocks edits, which the service enforces on save.
        dialog = InvoiceModal(self, invoice=invoice)
        if not dialog.exec():
            return
        self._save(
            dialog.invoice(), is_update=True,
            partner_decision=dialog.wants_save_partner(),
        )

    def _on_post(self) -> None:
        invoice = self._selected()
        if invoice is None or invoice.status is InvoiceStatus.POSTED:
            return
        decision = self._resolve_partner(invoice)
        if decision is _CANCELLED:
            return
        try:
            self._service.post(invoice, save_new_partner=bool(decision))
        except Exception as exc:  # noqa: BLE001 — surface to user
            QMessageBox.warning(self, "Không thể ghi sổ", str(exc))
            return
        self._reload()

    def _on_delete(self) -> None:
        invoice = self._selected()
        if invoice is None:
            return
        if QMessageBox.question(self, "Xóa chứng từ", f"Xóa chứng từ '{invoice.ref}'?") != QMessageBox.Yes:
            return
        try:
            self._service.delete(invoice)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Không thể xóa", str(exc))
            return
        self._reload()

    def _on_fetch_email(self) -> None:
        """Lấy HĐĐT mới từ hộp thư → tạo chứng từ nháp, rồi nạp lại danh sách."""
        from data.email.imap_client import EmailFetchError
        from domain.services.invoice_import_service import InvoiceImportService

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = InvoiceImportService().run()
        except EmailFetchError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Lấy hóa đơn từ email", str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — surface to user
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Lấy hóa đơn từ email", f"Lỗi: {exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        msg = (
            f"Đã nhập {result.imported} hóa đơn mới.\n"
            f"Bỏ qua (đã có): {result.skipped}."
        )
        if result.unknown_partner:
            msg += (
                f"\n{result.unknown_partner} chứng từ có đối tác chưa có trong "
                "danh mục (xem báo đỏ)."
            )
        if result.errors:
            msg += "\n\nLỗi:\n" + "\n".join(result.errors[:5])
        QMessageBox.information(self, "Lấy hóa đơn từ email", msg)
        self._reload()

    def _on_save_unknown_partner(self) -> None:
        """Lưu đối tác của chứng từ đang chọn vào danh mục (từ báo đỏ)."""
        invoice = self._selected()
        if invoice is None:
            QMessageBox.information(
                self, "Lưu vào danh mục",
                f"Hãy chọn một chứng từ có {self._cfg.partner_noun} báo đỏ trước.",
            )
            return
        if not self._service.partner_is_unknown(invoice):
            QMessageBox.information(
                self, "Lưu vào danh mục",
                f"{self._cfg.partner_noun.capitalize()} của chứng từ này đã có "
                "trong danh mục.",
            )
            return
        try:
            self._service.update(invoice, save_new_partner=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Không thể lưu", str(exc))
            return
        self._reload()

    def _save(
        self, invoice: Invoice, *, is_update: bool,
        partner_decision: bool | None = None,
    ) -> None:
        # Modal đã trả lời qua báo đỏ (True) thì dùng luôn; chưa trả lời (None)
        # mà đối tác vẫn lạ → hỏi tiếp bằng hộp thoại như trước.
        if partner_decision is None:
            decision = self._resolve_partner(invoice)
            if decision is _CANCELLED:
                return
        else:
            decision = partner_decision
        try:
            if is_update:
                self._service.update(invoice, save_new_partner=bool(decision))
            else:
                self._service.create(invoice, save_new_partner=bool(decision))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Không thể lưu", str(exc))
            return
        self._reload()

    def _resolve_partner(self, invoice: Invoice):
        """system_routing.png branch: prompt to save an unknown partner.

        Returns True/False for the save decision, or ``_CANCELLED`` if the user
        backed out of the whole operation.
        """
        if invoice.is_guest or self._service.partner_exists(invoice.partner_code):
            return False
        label = invoice.partner_name or invoice.partner_code
        answer = QMessageBox.question(
            self, "Lưu vào danh mục?",
            f"{self._cfg.partner_noun.capitalize()} '{label}' chưa có trong danh mục.\n"
            f"Lưu vào danh mục {self._cfg.partner_noun}?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        )
        if answer == QMessageBox.Cancel:
            return _CANCELLED
        return answer == QMessageBox.Yes

    def _selected(self) -> Invoice | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        invoice_id = item.data(Qt.UserRole)
        for inv in self._service.list_all():
            if inv.id == invoice_id:
                return inv
        return None

    @staticmethod
    def _configure_table(table: QTableWidget) -> None:
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
