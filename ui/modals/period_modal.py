"""PeriodModal: pick the active accounting period (tháng / quý / năm)."""
from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.period import Period


class PeriodModal(QDialog):
    def __init__(self, parent: QWidget | None = None, *, current: Period | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PeriodModal")
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setWindowTitle("Kỳ kế toán")

        current = current or Period(year=date.today().year, month=None)
        this_year = date.today().year

        self._year = QComboBox()
        # Đủ rộng để xem lại chứng từ cũ nhập từ email/hóa đơn lưu trữ — 6 năm
        # không đủ, hộp thư còn hóa đơn từ nhiều năm trước.
        for y in range(this_year - 12, this_year + 2):
            self._year.addItem(str(y), y)
        yi = self._year.findData(current.year)
        self._year.setCurrentIndex(yi if yi >= 0 else self._year.count() - 2)

        self._quarter = QComboBox()
        self._quarter.addItem("Cả năm", None)
        for q in range(1, 5):
            first = (q - 1) * 3 + 1
            self._quarter.addItem(f"Quý {q} (tháng {first:02d}–{first + 2:02d})", q)
        qi = self._quarter.findData(current.quarter)
        if qi >= 0:
            self._quarter.setCurrentIndex(qi)

        self._month = QComboBox()
        self._month.addItem("Cả năm", None)
        for m in range(1, 13):
            self._month.addItem(f"Tháng {m:02d}", m)
        mi = self._month.findData(current.month)
        if mi >= 0:
            self._month.setCurrentIndex(mi)

        # Tháng và quý loại trừ nhau: chọn cái này thì cái kia về "Cả năm",
        # nếu không người dùng không đoán được kỳ cuối cùng là kỳ nào.
        self._quarter.currentIndexChanged.connect(self._on_quarter_changed)
        self._month.currentIndexChanged.connect(self._on_month_changed)

        note = QLabel(
            "Chọn kỳ để lọc bút toán, hóa đơn… theo tháng, theo quý hoặc cả năm. "
            "Chọn tháng thì quý tự bỏ, và ngược lại."
        )
        note.setObjectName("SettingsNote")
        note.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Năm", self._year)
        form.addRow("Quý", self._quarter)
        form.addRow("Tháng", self._month)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Áp dụng")
        buttons.button(QDialogButtonBox.Cancel).setText("Hủy")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    # ----- loại trừ tháng ↔ quý --------------------------------------------

    def _on_quarter_changed(self) -> None:
        if self._quarter.currentData() is not None:
            self._reset(self._month)

    def _on_month_changed(self) -> None:
        if self._month.currentData() is not None:
            self._reset(self._quarter)

    @staticmethod
    def _reset(combo: QComboBox) -> None:
        """Về "Cả năm" mà không kích hoạt lại phía bên kia."""
        blocked = combo.blockSignals(True)
        combo.setCurrentIndex(0)
        combo.blockSignals(blocked)

    def period(self) -> Period:
        return Period(
            year=self._year.currentData(),
            month=self._month.currentData(),
            quarter=self._quarter.currentData(),
        )
