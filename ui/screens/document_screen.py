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
    QProgressDialog,
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
        btn_post_all = Button("Ghi sổ tất cả", icon_name="check")
        btn_post_all.clicked.connect(self._on_post_all)
        btn_delete = Button("Xóa", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_delete.clicked.connect(self._on_delete)
        btn_email = Button("Lấy từ email", icon_name="invoice")
        btn_email.clicked.connect(self._on_fetch_email)
        self._btn_email = btn_email
        self._email_worker = None  # QThread đang chạy (nếu có)

        toolbar.addWidget(self._search, 1)
        toolbar.addWidget(btn_email)
        toolbar.addWidget(btn_edit)
        toolbar.addWidget(self._btn_post)
        toolbar.addWidget(btn_post_all)
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
        # Chọn nhiều chứng từ: Ctrl+click từng dòng, Shift+click cả dải, Ctrl+A
        # chọn hết — rồi bấm Ghi sổ / Xóa để xử lý hàng loạt.
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setToolTip(
            "Ctrl+click chọn từng dòng · Shift+click chọn cả dải · Ctrl+A chọn tất "
            "cả.\nSau đó bấm Ghi sổ hoặc Xóa để xử lý hàng loạt."
        )
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
        # Sửa mở form chi tiết nên chỉ làm việc với đúng một chứng từ.
        if len(self._selected_many()) > 1:
            QMessageBox.information(
                self, "Sửa chứng từ",
                "Chỉ sửa được từng chứng từ một. Hãy chọn đúng một dòng.\n"
                "Chọn nhiều dòng chỉ dùng để Ghi sổ hoặc Xóa hàng loạt.")
            return
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
        """Ghi sổ mọi chứng từ đang chọn (một hoặc nhiều)."""
        self._bulk_post(self._selected_many(), source="đang chọn")

    def _on_post_all(self) -> None:
        """Ghi sổ toàn bộ chứng từ đang hiển thị (theo kỳ + ô tìm kiếm)."""
        self._bulk_post(self._visible_invoices(), source="trong danh sách")

    def _bulk_post(self, invoices: list[Invoice], *, source: str) -> None:
        targets = [i for i in invoices if i.status is not InvoiceStatus.POSTED]
        if not targets:
            QMessageBox.information(
                self, "Ghi sổ",
                f"Không có chứng từ nháp nào {source} để ghi sổ.")
            return

        # Hỏi MỘT lần cho cả lô thay vì mỗi chứng từ một hộp thoại.
        decision = self._resolve_partners_bulk(targets)
        if decision is _CANCELLED:
            return
        if len(targets) > 1 and QMessageBox.question(
            self, "Ghi sổ hàng loạt",
            f"Ghi sổ {len(targets)} chứng từ {source}?\n"
            "Thao tác này tạo bút toán vào sổ nhật ký chung.",
        ) != QMessageBox.Yes:
            return

        done, errors = self._run_batch(
            targets, "Đang ghi sổ…",
            lambda inv: self._service.post(inv, save_new_partner=bool(decision)),
        )
        self._reload()
        self._report_batch("Ghi sổ", done, errors, verb="ghi sổ")

    def _on_delete(self) -> None:
        invoices = self._selected_many()
        if not invoices:
            return
        if len(invoices) == 1:
            question = f"Xóa chứng từ '{invoices[0].ref}'?"
        else:
            question = (
                f"Xóa {len(invoices)} chứng từ đang chọn?\n"
                "Thao tác này không thể hoàn tác."
            )
        if QMessageBox.question(self, "Xóa chứng từ", question) != QMessageBox.Yes:
            return
        done, errors = self._run_batch(
            invoices, "Đang xóa…", self._service.delete)
        self._reload()
        self._report_batch("Xóa chứng từ", done, errors, verb="xóa")

    # ----- xử lý hàng loạt ------------------------------------------------

    def _run_batch(self, invoices: list[Invoice], label: str, action):
        """Chạy ``action`` cho từng chứng từ, có thanh tiến độ và nút Hủy.

        Ghi DB phải ở main thread (SQLite dùng chung kết nối), nên giữ giao diện
        sống bằng QProgressDialog thay vì đẩy sang thread.
        """
        errors: list[str] = []
        done = 0
        progress = QProgressDialog(label, "Hủy", 0, len(invoices), self)
        progress.setWindowTitle(label)
        progress.setMinimumDuration(0)  # hiện ngay, kể cả lô nhỏ
        progress.setWindowModality(Qt.WindowModal)
        for index, invoice in enumerate(invoices):
            if progress.wasCanceled():
                break
            progress.setValue(index)
            QApplication.processEvents()
            try:
                action(invoice)
                done += 1
            except Exception as exc:  # noqa: BLE001 — gom lại, báo cuối lô
                errors.append(f"{invoice.ref}: {exc}")
        progress.setValue(len(invoices))
        return done, errors

    def _report_batch(
        self, title: str, done: int, errors: list[str], *, verb: str
    ) -> None:
        if not errors:
            QMessageBox.information(self, title, f"Đã {verb} {done} chứng từ.")
            return
        detail = "\n".join(errors[:10])
        if len(errors) > 10:
            detail += f"\n… và {len(errors) - 10} lỗi khác."
        QMessageBox.warning(
            self, title,
            f"Đã {verb} {done} chứng từ.\nKhông {verb} được {len(errors)}:\n\n{detail}",
        )

    def _on_fetch_email(self) -> None:
        """Lấy HĐĐT mới từ hộp thư → tạo chứng từ nháp, rồi nạp lại danh sách.

        Pha mạng chạy trong QThread (app vẫn dùng được, không đứng hình); pha ghi
        DB chạy lại trên main thread ở ``_on_email_fetched`` vì SQLite dùng chung
        một kết nối.
        """
        from app.email_poller import FetchWorker
        from data.email.imap_client import EmailFetchError
        from domain.services.email_config_service import EmailConfigService
        from domain.services.invoice_import_service import InvoiceImportService

        if self._email_worker is not None and self._email_worker.isRunning():
            return  # đang chạy → bỏ qua cú bấm thừa

        self._email_cfg = EmailConfigService()
        config = self._email_cfg.load()
        if not config.is_ready:
            QMessageBox.warning(
                self, "Lấy hóa đơn từ email",
                "Chưa cấu hình email. Vào Cấu hình › Email / Hóa đơn điện tử.")
            return

        self._importer = InvoiceImportService(email_config=self._email_cfg)
        self._btn_email.setEnabled(False)
        self._btn_email.setText("Đang lấy…")
        worker = FetchWorker(self._importer, config)
        worker.progress.connect(self._on_email_progress)
        worker.fetched.connect(self._on_email_fetched)
        worker.finished.connect(worker.deleteLater)
        self._email_worker = worker
        self._email_error_type = EmailFetchError
        worker.start()

    def _on_email_progress(self, done: int, total: int) -> None:
        self._btn_email.setText(f"Đang lấy… {done}/{total}")

    def _on_email_fetched(self, items, max_uid: int, error) -> None:
        """Chạy trên main thread: ghi DB rồi báo kết quả."""
        self._email_worker = None
        self._btn_email.setText("Lấy từ email")
        self._btn_email.setEnabled(True)

        if error is not None:
            text = (
                str(error) if isinstance(error, self._email_error_type)
                else f"Lỗi: {error}"
            )
            QMessageBox.warning(self, "Lấy hóa đơn từ email", text)
            return

        result = self._importer.persist(items)
        if max_uid > self._email_cfg.load().last_uid:
            self._email_cfg.set_last_uid(max_uid)

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

    def _resolve_partners_bulk(self, invoices: list[Invoice]):
        """Hỏi một lần: có lưu các đối tác lạ của cả lô vào danh mục không?

        Trả True/False, hoặc ``_CANCELLED`` nếu người dùng hủy cả thao tác.
        """
        unknown = [
            inv for inv in invoices
            if not inv.is_guest and not self._service.partner_exists(inv.partner_code)
        ]
        if not unknown:
            return False
        noun = self._cfg.partner_noun
        if len(unknown) == 1:
            label = unknown[0].partner_name or unknown[0].partner_code
            text = (
                f"{noun.capitalize()} '{label}' chưa có trong danh mục.\n"
                f"Lưu vào danh mục {noun}?"
            )
        else:
            text = (
                f"{len(unknown)} chứng từ có {noun} chưa có trong danh mục.\n"
                f"Lưu tất cả vào danh mục {noun}?"
            )
        answer = QMessageBox.question(
            self, "Lưu vào danh mục?", text,
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        )
        if answer == QMessageBox.Cancel:
            return _CANCELLED
        return answer == QMessageBox.Yes

    def _selected_many(self) -> list[Invoice]:
        """Chứng từ ở mọi dòng đang chọn, theo thứ tự hiển thị."""
        model = self._table.selectionModel()
        rows = sorted(i.row() for i in model.selectedRows()) if model else []
        if not rows:
            invoice = self._selected()
            return [invoice] if invoice is not None else []
        return self._invoices_at(rows)

    def _visible_invoices(self) -> list[Invoice]:
        """Toàn bộ chứng từ đang hiển thị (đã lọc theo kỳ + ô tìm kiếm)."""
        return self._invoices_at(range(self._table.rowCount()))

    def _invoices_at(self, rows) -> list[Invoice]:
        """Nạp danh mục MỘT lần rồi tra theo id — tránh quét lại sổ mỗi dòng."""
        by_id = {inv.id: inv for inv in self._service.list_all()}
        found = []
        for row in rows:
            item = self._table.item(row, 0)
            if item is None:
                continue
            invoice = by_id.get(item.data(Qt.UserRole))
            if invoice is not None:
                found.append(invoice)
        return found

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
