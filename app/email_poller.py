"""EmailPoller: nền kiểm tra hộp thư định kỳ để tự nhập HĐĐT.

An toàn luồng: pha mạng (IMAP + phân tích XML) chạy trong QThread; pha ghi DB
(persist) chạy lại trên main thread qua signal — giữ mọi thao tác SQLite ở GUI
thread (kết nối dùng chung). Lỗi mạng được nuốt im lặng để không quấy rầy người
dùng; nút "Lấy từ email" thủ công mới báo lỗi tường minh.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from domain.services.email_config_service import EmailConfig, EmailConfigService
from domain.services.invoice_import_service import (
    ImportResult,
    InvoiceImportService,
    ParsedEmailInvoice,
)


class _FetchWorker(QThread):
    """Chạy fetch_parsed (chỉ mạng) ngoài GUI thread."""

    fetched = Signal(object, int, object)  # items, max_uid, error|None

    def __init__(self, importer: InvoiceImportService, config: EmailConfig) -> None:
        super().__init__()
        self._importer = importer
        self._config = config

    def run(self) -> None:  # noqa: D401 — QThread entrypoint
        try:
            items, max_uid = self._importer.fetch_parsed(self._config)
            self.fetched.emit(items, max_uid, None)
        except Exception as exc:  # noqa: BLE001 — báo về main thread, không crash
            self.fetched.emit([], self._config.last_uid, exc)


class EmailPoller(QObject):
    imported = Signal(object)  # ImportResult — chỉ phát khi có HĐ mới được nhập

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config_service = EmailConfigService()
        self._importer = InvoiceImportService(email_config=self._config_service)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._worker: _FetchWorker | None = None

    def start(self) -> None:
        """Bật hẹn giờ nếu người dùng đã bật tự động và cấu hình đủ thông tin."""
        config = self._config_service.load()
        if not config.auto_enabled or not config.is_ready:
            return
        self._timer.setInterval(max(1, config.poll_minutes) * 60_000)
        self._timer.start()
        QTimer.singleShot(5_000, self._tick)  # kiểm tra lần đầu ngay sau khi mở app

    def stop(self) -> None:
        self._timer.stop()
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3_000)

    # ----- vòng kiểm tra ---------------------------------------------------

    def _tick(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return  # lần trước chưa xong → bỏ qua nhịp này
        config = self._config_service.load()
        if not config.auto_enabled or not config.is_ready:
            self._timer.stop()
            return
        self._worker = _FetchWorker(self._importer, config)
        self._worker.fetched.connect(self._on_fetched)
        self._worker.start()

    def _on_fetched(
        self,
        items: list[ParsedEmailInvoice],
        max_uid: int,
        error: object,
    ) -> None:
        # Chạy trên main thread (signal/slot qua hàng đợi sự kiện) → ghi DB an toàn.
        if error is None and items:
            result: ImportResult = self._importer.persist(items)
            config = self._config_service.load()
            if max_uid > config.last_uid:
                self._config_service.set_last_uid(max_uid)
            if result.imported:
                self.imported.emit(result)
        elif error is None and max_uid:
            # Không có hóa đơn mới nhưng vẫn tiến UID để khỏi quét lại thư cũ.
            config = self._config_service.load()
            if max_uid > config.last_uid:
                self._config_service.set_last_uid(max_uid)
        self._worker = None
