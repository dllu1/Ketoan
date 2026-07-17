"""PeriodModal: pick the active accounting period (tháng / năm hoặc cả năm)."""
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
        for y in range(this_year - 6, this_year + 2):
            self._year.addItem(str(y), y)
        yi = self._year.findData(current.year)
        self._year.setCurrentIndex(yi if yi >= 0 else self._year.count() - 2)

        self._month = QComboBox()
        self._month.addItem("Cả năm", None)
        for m in range(1, 13):
            self._month.addItem(f"Tháng {m:02d}", m)
        mi = self._month.findData(current.month)
        if mi >= 0:
            self._month.setCurrentIndex(mi)

        note = QLabel("Chọn kỳ để lọc bút toán, hóa đơn… theo tháng hoặc cả năm.")
        note.setObjectName("SettingsNote")
        note.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Năm", self._year)
        form.addRow("Kỳ", self._month)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Áp dụng")
        buttons.button(QDialogButtonBox.Cancel).setText("Hủy")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def period(self) -> Period:
        return Period(year=self._year.currentData(), month=self._month.currentData())
