"""Dòng CỘNG ở chân "Bảng kê NVL chính" không được lẫn vào dữ liệu.

Bảng này sửa được, nên một dòng chân nằm chung trong QTableWidget rất dễ bị các
vòng lặp theo ``rowCount()`` nuốt vào: lưu thành một vật tư rác, bị nút "Xóa
dòng" xóa mất, hay nuốt con trỏ khi Enter ở ô cuối. Các test dưới đây chốt lại
ranh giới đó.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.period import Period, set_active_period  # noqa: E402


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.config.DB_PATH", db_file)
    monkeypatch.setattr("data.database.DB_PATH", db_file)

    import data.database as db_mod
    db_mod._conn = None
    db_mod.init_database()
    yield db_mod.get_connection()
    db_mod.close_connection()


@pytest.fixture
def june(app, temp_db):
    set_active_period(Period(year=2026, month=6))
    return temp_db


def _view():
    from ui.screens.material_sheet_view import MaterialSheetView

    return MaterialSheetView()


def _fill(view, row, *, code, name, unit, in_qty, in_value):
    from ui.screens import material_sheet_view as msv

    view._table.item(row, msv._CODE).setText(code)
    view._table.item(row, msv._NAME).setText(name)
    view._table.item(row, msv._UNIT).setText(unit)
    view._table.item(row, msv._I_QTY).setText(str(in_qty))
    view._table.item(row, msv._I_VAL).setText(str(in_value))


def test_footer_totals_every_numeric_column(june):
    from ui.screens import material_sheet_view as msv

    view = _view()
    _fill(view, 0, code="NVL1", name="Thép tấm", unit="kg",
          in_qty=10, in_value=10_000)
    view._add_row()
    _fill(view, 1, code="NVL2", name="Bu lông", unit="con",
          in_qty=5, in_value=2_500)

    footer = view._table.rowCount() - 1
    assert view._has_footer
    assert view._table.item(footer, msv._NAME).text() == "CỘNG"
    assert view._table.item(footer, msv._I_VAL).text() == "12,500"
    assert view._table.item(footer, msv._C_VAL).text() == "12,500"
    # Cột SL cũng cộng, dù hai dòng khác ĐVT (kg vs con).
    assert view._table.item(footer, msv._I_QTY).text() == "15"
    assert view._table.item(footer, msv._C_QTY).text() == "15"
    assert view._table.item(footer, msv._X_QTY).text() == "0"
    # Cột chữ (mã, ĐVT) không có gì để cộng.
    assert view._table.item(footer, msv._UNIT).text() == ""


def test_footer_is_not_saved_as_a_material(june):
    view = _view()
    _fill(view, 0, code="NVL1", name="Thép tấm", unit="kg",
          in_qty=10, in_value=10_000)

    assert [ln.code for ln in view._sheet().lines] == ["NVL1"]

    view._service.save(view._sheet())
    from data.repositories.material_sheet_repo import MaterialSheetRepository
    saved = MaterialSheetRepository().list_for_period("2026-06")
    assert [ln.code for ln in saved] == ["NVL1"]
    assert saved[0].in_value == Decimal("10000")


def test_delete_button_cannot_remove_the_footer(june):
    view = _view()
    _fill(view, 0, code="NVL1", name="Thép tấm", unit="kg",
          in_qty=10, in_value=10_000)

    footer = view._table.rowCount() - 1
    view._table.setCurrentCell(footer, 0)
    view._remove_current_row()

    assert view._has_footer
    assert view._data_row_count() == 1
    assert [ln.code for ln in view._sheet().lines] == ["NVL1"]


def test_enter_at_last_cell_lands_on_the_new_row_not_the_footer(june):
    view = _view()
    _fill(view, 0, code="NVL1", name="Thép tấm", unit="kg",
          in_qty=10, in_value=10_000)

    before = view._data_row_count()
    view._add_row_from_nav()

    assert view._data_row_count() == before + 1
    assert view._table.currentRow() == before        # dòng vật tư mới
    assert view._table.currentRow() != view._table.rowCount() - 1   # không phải CỘNG
