"""Tests for the raw-material NXT worksheet (Bảng kê N–X–T NVL chính).

Covers the derived closing balance (đầu kỳ + nhập − xuất) and, crucially, the
rule that a negative tồn cuối kỳ is refused at save — using a real row from the
source form (Sắt cây 30) whose closing value comes out negative.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.models.material_sheet import MaterialLine, MaterialSheet


@pytest.fixture
def in_memory_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.config.DB_PATH", db_file)
    monkeypatch.setattr("data.database.DB_PATH", db_file)

    import data.database as db_mod
    db_mod._conn = None
    db_mod.init_database()
    yield db_mod.get_connection()
    db_mod.close_connection()


def _service(conn):
    from data.repositories.material_sheet_repo import MaterialSheetRepository
    from domain.services.material_sheet_service import MaterialSheetService

    return MaterialSheetService(MaterialSheetRepository(conn))


def _line(**kw) -> MaterialLine:
    defaults = dict(code="S20", name="Sắt cây 20", unit="Kg")
    defaults.update(kw)
    return MaterialLine(**{k: (Decimal(str(v)) if isinstance(v, (int, float)) else v)
                           for k, v in defaults.items()})


# ----- pure model: derived closing balance --------------------------------


def test_closing_is_opening_plus_in_minus_out():
    line = _line(
        opening_qty=100, opening_value=1_000_000,
        in_qty=50, in_value=600_000,
        out_qty=30, out_value=360_000,
    )
    assert line.closing_qty == Decimal("120")
    assert line.closing_value == Decimal("1240000")
    assert not line.is_negative


def test_negative_closing_value_is_flagged():
    # Sắt cây 30 from the form: 70,202,969 + 1,038,154,624 − 1,235,261,997 < 0.
    line = _line(
        code="S30", name="Sắt cây 30",
        opening_qty=5_004, opening_value=70_202_969,
        in_qty=72_463, in_value=1_038_154_624,
        out_qty=86_337, out_value=1_235_261_997,
    )
    assert line.closing_value == Decimal("-126904404")
    assert line.is_negative


def test_negative_closing_qty_is_flagged():
    line = _line(opening_qty=10, in_qty=0, out_qty=15)
    assert line.closing_qty == Decimal("-5")
    assert line.is_negative


# ----- service: save guard + persistence ----------------------------------


def test_save_rejects_negative_closing(in_memory_db):
    from domain.services.material_sheet_service import MaterialSheetError

    svc = _service(in_memory_db)
    sheet = MaterialSheet(
        period_key="2026",
        lines=[
            _line(opening_qty=10, opening_value=100, in_qty=0, in_value=0,
                  out_qty=15, out_value=150),  # closing qty/value negative
        ],
    )
    assert sheet.has_negative_closing
    with pytest.raises(MaterialSheetError):
        svc.save(sheet)
    # Nothing persisted.
    assert svc.load("2026").lines == []


def test_save_then_load_round_trip(in_memory_db):
    svc = _service(in_memory_db)
    sheet = MaterialSheet(
        period_key="2026",
        lines=[
            _line(opening_qty=100, opening_value=1_000_000,
                  in_qty=50, in_value=600_000, out_qty=30, out_value=360_000),
        ],
    )
    svc.save(sheet)
    loaded = svc.load("2026")
    assert len(loaded.lines) == 1
    assert loaded.lines[0].code == "S20"
    assert loaded.lines[0].closing_qty == Decimal("120")
    assert loaded.lines[0].closing_value == Decimal("1240000")
    assert not loaded.has_negative_closing


def test_empty_rows_are_dropped_on_save(in_memory_db):
    svc = _service(in_memory_db)
    sheet = MaterialSheet(
        period_key="2026",
        lines=[
            _line(opening_qty=100, opening_value=1_000_000),
            MaterialLine(code="", name="", unit=""),  # blank row
        ],
    )
    svc.save(sheet)
    assert len(svc.load("2026").lines) == 1
