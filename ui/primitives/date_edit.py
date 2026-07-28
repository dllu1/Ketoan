"""DateEdit: ô ngày tháng cho phép **xóa trắng rồi gõ tay** cả ngày/tháng/năm.

``QDateEdit`` gốc khóa ô theo từng mảnh (dd · MM · yyyy): không xóa hết được,
phải mũi tên / gõ đè từng mảnh. Kế toán nhập liệu nhanh muốn bôi đen → xóa →
gõ liền ``01/02/2026`` (hoặc ``01022026``, ``1-2-26``) rồi Enter.

Cách làm: khi người dùng bôi đen toàn bộ và bấm Delete/Backspace, ô chuyển sang
*chế độ gõ tự do* — tạm gỡ validator nội bộ của QDateTimeEdit và ngắt tín hiệu
của line edit để Qt không viết đè text đang gõ dở. Enter / Tab / mất focus sẽ
diễn giải chuỗi; không đọc được thì trả về ngày cũ (không bao giờ để ô rỗng).
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QDateEdit, QWidget

# Các dạng chấp nhận khi gõ tay, thử theo thứ tự.
_PARSE_FORMATS = (
    "dd/MM/yyyy", "d/M/yyyy", "dd-MM-yyyy", "d-M-yyyy",
    "dd.MM.yyyy", "d.M.yyyy", "ddMMyyyy",
    "dd/MM/yy", "d/M/yy", "ddMMyy",
)


class DateEdit(QDateEdit):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        value: date | QDate | None = None,
        calendar: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setCalendarPopup(calendar)
        self.setDisplayFormat("dd/MM/yyyy")
        self.setDate(_as_qdate(value) if value is not None else QDate.currentDate())
        self.setToolTip("Bôi đen (Ctrl+A) rồi Delete để xóa trắng và gõ tay, vd 01/02/2026")
        self._free = False
        self._saved_validator = None

    # ----- gõ tự do ------------------------------------------------------

    @property
    def is_free_typing(self) -> bool:
        """Ô đang ở chế độ gõ tay (đã xóa trắng, chưa diễn giải)."""
        return self._free

    def _begin_free_typing(self) -> None:
        line = self.lineEdit()
        self._saved_validator = line.validator()
        line.setValidator(None)
        # Ngắt textChanged: QAbstractSpinBox nghe tín hiệu này để "sửa" lại chuỗi
        # về một ngày hợp lệ — đúng thứ đang cần tránh khi gõ dở.
        line.blockSignals(True)
        line.clear()
        self._free = True

    def _end_free_typing(self) -> str:
        line = self.lineEdit()
        text = line.text().strip()
        line.blockSignals(False)
        line.setValidator(self._saved_validator)
        self._saved_validator = None
        self._free = False
        return text

    def _commit_free_typing(self) -> None:
        text = self._end_free_typing()
        parsed = parse_date_text(text)
        # Không đọc được (kể cả ô rỗng) → giữ nguyên ngày trước đó.
        self.setDate(parsed if parsed is not None else self.date())
        # setDate không tự vẽ lại khi ngày không đổi; ép line edit về đúng định dạng.
        self.lineEdit().setText(self.date().toString(self.displayFormat()))

    def _cancel_free_typing(self) -> None:
        self._end_free_typing()
        self.lineEdit().setText(self.date().toString(self.displayFormat()))

    # ----- Qt overrides --------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        line = self.lineEdit()
        key = event.key()
        if not self._free:
            selected_all = bool(line.text()) and line.selectedText() == line.text()
            if selected_all and key in (Qt.Key_Delete, Qt.Key_Backspace):
                self._begin_free_typing()
                return
            super().keyPressEvent(event)
            return

        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab, Qt.Key_Backtab):
            self._commit_free_typing()
            # Để Enter/Tab đi tiếp: nhảy ô (enter_nav) hoặc chuyển focus.
            super().keyPressEvent(event)
            return
        if key == Qt.Key_Escape:
            self._cancel_free_typing()
            return
        # QAbstractSpinBox là focus proxy của line edit, nên phím tới đây trước;
        # chuyển thẳng cho line edit như bản gốc vẫn làm (không đệ quy).
        line.event(event)

    def focusOutEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        if self._free:
            self._commit_free_typing()
        super().focusOutEvent(event)

    # ----- tiện ích ------------------------------------------------------

    def date_value(self) -> date:
        """Ngày hiện tại dưới dạng ``datetime.date`` (đã diễn giải nếu đang gõ dở)."""
        if self._free:
            self._commit_free_typing()
        qd = self.date()
        return date(qd.year(), qd.month(), qd.day())


def parse_date_text(text: str) -> QDate | None:
    """Diễn giải chuỗi ngày người dùng gõ tay; ``None`` nếu không đọc được."""
    text = text.strip()
    if not text:
        return None
    for fmt in _PARSE_FORMATS:
        qd = QDate.fromString(text, fmt)
        if qd.isValid():
            return qd
    return None


def _as_qdate(value: date | QDate) -> QDate:
    if isinstance(value, QDate):
        return value
    return QDate(value.year, value.month, value.day)
