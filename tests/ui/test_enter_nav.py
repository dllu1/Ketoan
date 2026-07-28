"""Enter = nhảy ô kế tiếp trên lưới nhập liệu.

Chạy headless (QT_QPA_PLATFORM=offscreen) nên không cần màn hình thật.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem  # noqa: E402

from ui.primitives.enter_nav import (  # noqa: E402
    advance_to_next_cell,
    first_editable_cell,
    install_grid_enter_nav,
    next_editable_cell,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _table(rows: int = 2, columns: int = 3, *, readonly: tuple[int, ...] = ()) -> QTableWidget:
    table = QTableWidget(rows, columns)
    for row in range(rows):
        for col in range(columns):
            item = QTableWidgetItem("")
            if col in readonly:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, col, item)
    return table


def test_next_editable_cell_walks_along_the_row(app):
    table = _table()
    assert next_editable_cell(table, 0, 0) == (0, 1)
    assert next_editable_cell(table, 0, 1) == (0, 2)


def test_next_editable_cell_wraps_to_the_following_row(app):
    table = _table()
    assert next_editable_cell(table, 0, 2) == (1, 0)


def test_next_editable_cell_skips_read_only_columns(app):
    """Cột "Thành tiền" là ô tính sẵn — Enter phải bỏ qua, không dừng ở đó."""
    table = _table(readonly=(2,))
    assert next_editable_cell(table, 0, 1) == (1, 0)


def test_next_editable_cell_returns_none_at_the_end_of_the_grid(app):
    table = _table(rows=1, columns=2)
    assert next_editable_cell(table, 0, 1) is None


def test_first_editable_cell_skips_a_read_only_first_column(app):
    table = _table(readonly=(0,))
    assert first_editable_cell(table, 0) == (0, 1)


def test_advance_moves_the_current_cell(app):
    table = _table()
    install_grid_enter_nav(table)
    table.setCurrentCell(0, 0)

    advance_to_next_cell(table)

    assert (table.currentRow(), table.currentColumn()) == (0, 1)


def test_advance_at_the_last_cell_adds_a_row_when_allowed(app):
    """Nhập liên tục: Enter ở ô cuối mở luôn dòng mới, không phải bấm "+ Thêm dòng"."""
    table = _table(rows=1, columns=2)

    def add_row() -> None:
        row = table.rowCount()
        table.insertRow(row)
        for col in range(table.columnCount()):
            table.setItem(row, col, QTableWidgetItem(""))

    install_grid_enter_nav(table, add_row=add_row)
    table.setCurrentCell(0, 1)

    advance_to_next_cell(table)

    assert table.rowCount() == 2
    assert (table.currentRow(), table.currentColumn()) == (1, 0)


def test_advance_at_the_last_cell_stays_put_without_an_add_row_hook(app):
    table = _table(rows=1, columns=2)
    install_grid_enter_nav(table)
    table.setCurrentCell(0, 1)

    advance_to_next_cell(table)

    assert table.rowCount() == 1
    assert (table.currentRow(), table.currentColumn()) == (0, 1)
