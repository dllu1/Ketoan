"""ReportViewScreen: shared report viewer/exporter base (Phase 4).

Holds everything common to the Financial Reports and Tax Reports screens — the
report switcher, the date range, the table renderer (homogeneous *and*
heterogeneous multi-table documents), and the Excel/PDF export flow. Subclasses
only declare their report list and map a report key to a :class:`ReportDocument`.
"""
from __future__ import annotations

import unicodedata
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from domain.models.report import ReportPeriod
from reports.report_tables import ReportDocument, format_cell
from ui.primitives.button import Button, ButtonVariant
from ui.primitives.segmented import Segmented


_MAX_AUTO_WIDTH = 430   # cap for content-fitted columns (px); user can drag wider


class ReportViewScreen(QWidget):
    TITLE: str = "Báo cáo"
    OPTIONS: list[tuple[str, str]] = []
    DEFAULT: str | None = None

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName(self.__class__.__name__)
        self._document: ReportDocument | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel(self.TITLE)
        title.setObjectName("ScreenTitle")
        root.addWidget(title)

        root.addLayout(self._build_toolbar())

        self._table = QTableWidget(0, 0)
        self._table.setObjectName("ReportTable")
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self._table, 1)

        self._summary = QLabel("")
        self._summary.setObjectName("SectionLabel")
        root.addWidget(self._summary)

        self._refresh()

    # ----- subclass hooks ---------------------------------------------------

    def _new_services(self) -> None:
        """Rebuild service objects so each refresh reads live ledger state."""

    def _dispatch(self, key: str, period: ReportPeriod) -> ReportDocument:
        raise NotImplementedError

    def _account_filter_keys(self) -> set[str]:
        """Report keys that expose the 'tìm theo số tài khoản' search box."""
        return set()

    def _account_query(self) -> str:
        return self._account_filter.text().strip()

    # ----- toolbar ----------------------------------------------------------

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(10)

        default = self.DEFAULT or (self.OPTIONS[0][0] if self.OPTIONS else None)
        self._switcher = Segmented(list(self.OPTIONS), default=default)
        self._switcher.selection_changed.connect(lambda _: self._refresh())

        # Tìm theo số tài khoản — chỉ hiện với các báo cáo đã đăng ký
        # (vd: Sổ cái). Mặc định ẩn.
        self._account_filter = QLineEdit()
        self._account_filter.setPlaceholderText("Số tài khoản (vd: 131)")
        self._account_filter.setMaximumWidth(180)
        self._account_filter.setClearButtonEnabled(True)
        self._account_filter.textChanged.connect(lambda _: self._refresh())
        self._account_filter.hide()

        today = QDate.currentDate()
        self._from = self._make_date(QDate(today.year(), 1, 1))
        self._to = self._make_date(today)
        self._from.dateChanged.connect(lambda _: self._refresh())
        self._to.dateChanged.connect(lambda _: self._refresh())

        btn_xlsx = Button("Xuất Excel", icon_name="download")
        btn_xlsx.clicked.connect(lambda: self._export("xlsx"))
        btn_pdf = Button("Xuất PDF", variant=ButtonVariant.PRIMARY, icon_name="print")
        btn_pdf.clicked.connect(lambda: self._export("pdf"))

        bar.addWidget(self._switcher)
        bar.addWidget(self._account_filter)
        bar.addStretch(1)
        bar.addWidget(QLabel("Từ"))
        bar.addWidget(self._from)
        bar.addWidget(QLabel("đến"))
        bar.addWidget(self._to)
        bar.addWidget(btn_xlsx)
        bar.addWidget(btn_pdf)
        return bar

    @staticmethod
    def _make_date(value: QDate) -> QDateEdit:
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("dd/MM/yyyy")
        edit.setDate(value)
        return edit

    # ----- build + render ---------------------------------------------------

    def _period(self) -> ReportPeriod:
        return ReportPeriod(start=_to_date(self._from.date()), end=_to_date(self._to.date()))

    def _refresh(self) -> None:
        if not hasattr(self, "_switcher"):
            return
        self._new_services()
        key = self._switcher.active() or self.DEFAULT or self.OPTIONS[0][0]
        self._account_filter.setVisible(key in self._account_filter_keys())
        self._document = self._dispatch(key, self._period())
        self._render(self._document)

    def _render(self, doc: ReportDocument) -> None:
        self._table.clear()
        self._table.clearSpans()
        self._table.setRowCount(0)

        tables = doc.tables
        uniform = _uniform_columns(tables)
        col_count = max((len(t.columns) for t in tables), default=0)
        self._table.setColumnCount(col_count)

        header = self._table.horizontalHeader()
        if uniform is not None:
            # Homogeneous report: one fixed header bar; tables stack as sections.
            header.setVisible(True)
            self._table.setHorizontalHeaderLabels([c.header for c in uniform])
            for c, column in enumerate(uniform):
                header.setSectionResizeMode(
                    c, QHeaderView.ResizeToContents if column.numeric
                    else QHeaderView.Interactive
                )
            header.setSectionResizeMode(_stretch_column(uniform), QHeaderView.Stretch)
        else:
            # Heterogeneous report (e.g. VAT declaration + phụ lục): show a visible
            # header bar — labelled from the primary table — so its dividers can be
            # dragged. Each non-primary table still prints its own header row.
            header.setVisible(True)
            primary = [c.header for c in tables[0].columns] if tables else []
            primary += [""] * (col_count - len(primary))
            self._table.setHorizontalHeaderLabels(primary)
            for c in range(col_count):
                header.setSectionResizeMode(c, QHeaderView.Interactive)
            header.setStretchLastSection(False)

        for index, table in enumerate(tables):
            if table.caption:
                self._add_section_row(col_count, table.caption)
            # The primary heterogeneous table is already labelled by the header bar.
            if uniform is None and index != 0:
                self._add_row(table.columns, [c.header for c in table.columns],
                              bold=True, col_count=col_count)
            for row in table.rows:
                self._add_row(table.columns, row, bold=False, col_count=col_count)
            if table.total_row is not None:
                self._add_row(table.columns, table.total_row, bold=True,
                              col_count=col_count)

        if uniform is None:
            # Fit columns to their numbers so nothing is truncated, but keep any one
            # text column from running away (the user can still drag from here).
            self._table.resizeColumnsToContents()
            for c in range(col_count):
                if self._table.columnWidth(c) > _MAX_AUTO_WIDTH:
                    self._table.setColumnWidth(c, _MAX_AUTO_WIDTH)

        self._summary.setText(_summary_for(doc))

    def _add_row(self, columns, values, *, bold: bool, col_count: int) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        for c in range(col_count):
            column = columns[c] if c < len(columns) else None
            value = values[c] if c < len(values) else ""
            item = QTableWidgetItem(format_cell(value))
            if column is not None and column.numeric:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if bold:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self._table.setItem(row, c, item)

    def _add_section_row(self, col_count: int, text: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        item = QTableWidgetItem(text)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setForeground(QColor("#a1caff"))
        self._table.setItem(row, 0, item)
        if col_count > 1:
            self._table.setSpan(row, 0, 1, col_count)

    # ----- export -----------------------------------------------------------

    def _export(self, fmt: str) -> None:
        if self._document is None or not self._document.tables:
            return
        default_name = f"{_slug(self._document.title)}_{date.today():%Y%m%d}.{fmt}"
        caption = "Xuất Excel" if fmt == "xlsx" else "Xuất PDF"
        filt = "Excel (*.xlsx)" if fmt == "xlsx" else "PDF (*.pdf)"
        path, _ = QFileDialog.getSaveFileName(self, caption, default_name, filt)
        if not path:
            return
        try:
            if fmt == "xlsx":
                from reports.exporters import export_excel
                export_excel(self._document, path)
            else:
                from reports.exporters import export_pdf
                export_pdf(self._document, path)
        except ImportError:
            QMessageBox.warning(
                self, "Thiếu thư viện",
                "Cần cài đặt thư viện xuất báo cáo:\n"
                "pip install openpyxl reportlab",
            )
            return
        except Exception as exc:  # noqa: BLE001 — surface to user
            QMessageBox.warning(self, "Không thể xuất", str(exc))
            return
        QMessageBox.information(self, "Đã xuất báo cáo", f"Đã lưu:\n{path}")


# ----- helpers --------------------------------------------------------------


def _to_date(qd: QDate) -> date:
    return date(qd.year(), qd.month(), qd.day())


def _uniform_columns(tables):
    """Return the shared column schema if every table matches, else None.

    Homogeneous docs (journal, balance sheet) render under one header bar;
    heterogeneous docs (VAT: invoice lists + summary) fall back to per-table
    header rows.
    """
    if not tables:
        return []
    headers = [c.header for c in tables[0].columns]
    for table in tables[1:]:
        if [c.header for c in table.columns] != headers:
            return None
    return tables[0].columns


def _stretch_column(columns) -> int:
    """Stretch the first wide text column (description / account name)."""
    for c, column in enumerate(columns):
        if not column.numeric and column.header in (
            "Diễn giải", "Tên tài khoản", "Chỉ tiêu", "Tên người mua/bán"
        ):
            return c
    return max(0, len(columns) - 1)


def _summary_for(doc: ReportDocument) -> str:
    if not doc.tables or not any(t.rows for t in doc.tables):
        return "Không có dữ liệu trong kỳ."
    count = sum(len(t.rows) for t in doc.tables)
    return f"{doc.subtitle}   ·   {count} dòng"


def _slug(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return "_".join(ascii_only.split()) or "BaoCao"
