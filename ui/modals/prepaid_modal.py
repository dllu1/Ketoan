"""PrepaidModal — khai báo & xem lịch phân bổ chi phí trả trước (TK 242).

Lưới trên: danh sách khoản chi phí trả trước (mã · nội dung · số tiền · số tháng
· tháng bắt đầu · TK chi phí · TK treo). Lưới dưới: lịch phân bổ từng tháng của
khoản đang chọn (T01…T12 …) kèm lũy kế và số còn lại — đúng bảng trong sổ tay.
"""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.models.prepaid import PrepaidExpense
from domain.money import format_money, parse_money
from domain.services.prepaid_service import PrepaidService, PrepaidValidationError
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.enter_nav import install_grid_enter_nav

_HEADERS = ["Mã", "Nội dung", "Số tiền", "Số tháng", "Từ tháng", "Năm",
            "TK chi phí", "TK treo"]
(_C_CODE, _C_NAME, _C_TOTAL, _C_MONTHS, _C_MONTH, _C_YEAR,
 _C_EXPENSE, _C_ASSET) = range(8)

_SCHEDULE_HEADERS = ["Kỳ", "Phân bổ", "Lũy kế", "Còn lại"]


class PrepaidModal(QDialog):
    def __init__(self, parent: QWidget | None = None,
                 service: PrepaidService | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PrepaidModal")
        self.setModal(True)
        self.setMinimumSize(940, 620)
        self.setWindowTitle("Chi phí trả trước (TK 242)")

        self._service = service or PrepaidService()
        self._ids: dict[int, int | None] = {}   # row -> id trong DB

        title = QLabel("Chi phí trả trước · phân bổ dần")
        title.setObjectName("DialogTitle")
        subtitle = QLabel(
            "Khoản chi dùng cho nhiều kỳ: treo vào TK 242 rồi phân bổ đều theo "
            "số tháng. Mỗi tháng ghi Nợ TK chi phí / Có 242."
        )
        subtitle.setObjectName("DialogSubtitle")
        subtitle.setWordWrap(True)

        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        head = self._table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeToContents)
        head.setSectionResizeMode(_C_NAME, QHeaderView.Stretch)
        self._table.itemSelectionChanged.connect(self._refresh_schedule)
        install_grid_enter_nav(self._table, add_row=self._add_row)

        buttons = QHBoxLayout()
        btn_add = Button("+ Thêm khoản", icon_name="plus")
        btn_add.clicked.connect(lambda: self._add_row())
        btn_del = Button("− Xóa khoản", variant=ButtonVariant.DANGER, icon_name="trash")
        btn_del.clicked.connect(self._delete_row)
        btn_save = Button("Lưu", variant=ButtonVariant.PRIMARY, icon_name="check")
        btn_save.clicked.connect(self._save)
        buttons.addWidget(btn_add)
        buttons.addWidget(btn_del)
        buttons.addStretch(1)
        buttons.addWidget(btn_save)

        schedule_label = QLabel("LỊCH PHÂN BỔ CỦA KHOẢN ĐANG CHỌN")
        schedule_label.setObjectName("SectionLabel")
        self._schedule = QTableWidget(0, len(_SCHEDULE_HEADERS))
        self._schedule.setHorizontalHeaderLabels(_SCHEDULE_HEADERS)
        self._schedule.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._schedule.setAlternatingRowColors(True)
        self._schedule.verticalHeader().setVisible(False)
        self._schedule.setMaximumHeight(220)
        self._schedule.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        btn_close = Button("Đóng", variant=ButtonVariant.GHOST)
        btn_close.clicked.connect(self.accept)
        close_row.addWidget(btn_close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._table, 1)
        layout.addLayout(buttons)
        layout.addWidget(schedule_label)
        layout.addWidget(self._schedule)
        layout.addLayout(close_row)

        self._reload()

    # ----- data ----------------------------------------------------------

    def _reload(self) -> None:
        self._table.setRowCount(0)
        self._ids.clear()
        for prepaid in self._service.list_all():
            self._add_row(prepaid)
        if self._table.rowCount() == 0:
            self._add_row()
        # Chọn sẵn dòng đầu để lịch phân bổ hiện ngay, không phải bấm chuột.
        self._table.selectRow(0)
        self._refresh_schedule()

    def _add_row(self, prepaid: PrepaidExpense | None = None) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._ids[row] = prepaid.id if prepaid else None
        values = [
            prepaid.code if prepaid else "",
            prepaid.name if prepaid else "",
            format_money(prepaid.total_amount) if prepaid else "",
            str(prepaid.months) if prepaid else "12",
            f"{prepaid.start_month:02d}" if prepaid else "01",
            str(prepaid.start_year) if prepaid else "",
            prepaid.expense_account if prepaid else "642",
            prepaid.asset_account if prepaid else "242",
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col in (_C_TOTAL, _C_MONTHS, _C_MONTH, _C_YEAR):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, col, item)

    def _delete_row(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        prepaid_id = self._ids.get(row)
        if prepaid_id is not None:
            self._service.delete(prepaid_id)
        self._table.removeRow(row)
        # Dồn lại chỉ số dòng → id sau khi xóa.
        self._ids = {
            r: self._ids.get(r if r < row else r + 1)
            for r in range(self._table.rowCount())
        }
        self._refresh_schedule()

    def _row_to_prepaid(self, row: int) -> PrepaidExpense | None:
        code = self._text(row, _C_CODE)
        if not code:
            return None
        return PrepaidExpense(
            id=self._ids.get(row),
            code=code,
            name=self._text(row, _C_NAME),
            total_amount=self._money(row, _C_TOTAL),
            months=self._int(row, _C_MONTHS, default=1),
            start_year=self._int(row, _C_YEAR, default=0),
            start_month=self._int(row, _C_MONTH, default=1),
            expense_account=self._text(row, _C_EXPENSE) or "642",
            asset_account=self._text(row, _C_ASSET) or "242",
        )

    def _save(self) -> None:
        saved = 0
        for row in range(self._table.rowCount()):
            prepaid = self._row_to_prepaid(row)
            if prepaid is None:
                continue
            try:
                stored = self._service.save(prepaid)
            except PrepaidValidationError as exc:
                QMessageBox.warning(self, "Không thể lưu", f"Dòng {row + 1}: {exc}")
                return
            self._ids[row] = stored.id
            saved += 1
        QMessageBox.information(
            self, "Đã lưu", f"Đã lưu {saved} khoản chi phí trả trước."
        )
        self._refresh_schedule()

    # ----- lịch phân bổ ---------------------------------------------------

    def _refresh_schedule(self) -> None:
        self._schedule.setRowCount(0)
        row = self._table.currentRow()
        if row < 0:
            return
        prepaid = self._row_to_prepaid(row)
        if prepaid is None or prepaid.months <= 0 \
                or prepaid.total_amount <= Decimal("0"):
            return
        for entry in self._service.schedule(prepaid):
            r = self._schedule.rowCount()
            self._schedule.insertRow(r)
            for col, text in enumerate((
                entry.label, format_money(entry.amount),
                format_money(entry.allocated), format_money(entry.remaining),
            )):
                item = QTableWidgetItem(text)
                if col > 0:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._schedule.setItem(r, col, item)

    # ----- cell helpers ---------------------------------------------------

    def _text(self, row: int, col: int) -> str:
        item = self._table.item(row, col)
        return item.text().strip() if item else ""

    def _money(self, row: int, col: int) -> Decimal:
        try:
            return parse_money(self._text(row, col))
        except ValueError:
            return Decimal("0")

    def _int(self, row: int, col: int, *, default: int) -> int:
        try:
            return int(self._money(row, col))
        except (ValueError, ArithmeticError):
            return default
