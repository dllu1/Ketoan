"""ClosingScreen: lưới quy tắc kết chuyển đọc/ghi được và xem trước đúng số.

Chạy headless (QT_QPA_PLATFORM=offscreen) trên một SQLite tạm.
"""
from __future__ import annotations

from datetime import date
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


def _screen():
    from ui.screens.closing_screen import ClosingScreen

    set_active_period(Period(year=2026, month=None))
    return ClosingScreen()


def _post(conn, ref, debit_account, credit_account, amount):
    from data.repositories.journal_repo import JournalRepository
    from domain.models.journal import EntryStatus, JournalEntry, JournalLine
    from domain.services.journal_service import JournalService

    JournalService(JournalRepository(conn)).create(JournalEntry(
        ref=ref,
        entry_date=date(2026, 6, 15),
        status=EntryStatus.POSTED,
        lines=[
            JournalLine(account_code=debit_account, debit=Decimal(amount)),
            JournalLine(account_code=credit_account, credit=Decimal(amount)),
        ],
    ))


def test_screen_shows_the_default_rules(app, temp_db):
    screen = _screen()

    sources = {
        screen._table.item(row, 0).text()
        for row in range(screen._table.rowCount())
    }
    assert {"511", "515", "632", "642"} <= sources
    assert screen._result_account.text() == "911"
    assert screen._profit_account.text() == "4212"


def test_editing_the_grid_round_trips_through_the_service(app, temp_db):
    """Sửa số chứng từ trên lưới rồi lưu → nạp lại vẫn đúng."""
    from PySide6.QtWidgets import QTableWidgetItem

    from domain.models.transfer_rule import TransferDirection

    screen = _screen()
    row = next(
        r for r in range(screen._table.rowCount())
        if screen._table.item(r, 0).text() == "515"
    )
    screen._table.setItem(row, 5, QTableWidgetItem("KC-TC"))
    saved = screen._rules_service.save_rules(screen._collect_rules())

    rule = next(r for r in saved if r.source_account == "515")
    assert rule.group_ref == "KC-TC"
    assert rule.direction is TransferDirection.DEBIT_SOURCE
    assert rule.target_account == "911"


def test_preview_lists_the_pending_transfer(app, temp_db):
    screen = _screen()
    _post(temp_db, "BH01", "131", "511", "50000000")
    _post(temp_db, "QL01", "642", "111", "20000000")

    screen.on_activated()

    rows = [
        [screen._preview.item(r, c).text() for c in range(6)]
        for r in range(screen._preview.rowCount())
    ]
    assert any(
        r[0] == "KC-DT/2026" and r[1] == "511" and r[3] == "Nợ" and r[5] == "Có 911"
        for r in rows
    )
    assert any(r[1] == "642" and r[3] == "Có" and r[5] == "Nợ 911" for r in rows)
    assert "LÃI" in screen._preview_note.text()


def test_adding_an_empty_row_is_ignored_on_save(app, temp_db):
    screen = _screen()
    before = len(screen._collect_rules())

    screen._on_add_rule()

    assert screen._table.rowCount() == before + 1
    assert len(screen._collect_rules()) == before   # dòng trống không được lưu


# ----- chọn kết chuyển theo tháng / quý / năm ------------------------------


def _pick_scope(screen, scope, slot_value=None):
    """Chọn mức kết chuyển (và tháng/quý cụ thể) như người dùng bấm combo."""
    screen._scope.setCurrentIndex(screen._scope.findData(scope.value))
    if slot_value is not None:
        screen._slot.setCurrentIndex(screen._slot.findData(slot_value))


def test_scope_defaults_to_the_period_on_the_top_bar(app, temp_db):
    from app.period import PeriodScope
    from ui.screens.closing_screen import ClosingScreen

    set_active_period(Period(year=2026, quarter=2))
    screen = ClosingScreen()

    assert screen._selected_scope() is PeriodScope.QUARTER
    assert screen._closing_period() == Period(year=2026, quarter=2)


def test_switching_to_quarter_keeps_the_selected_month_inside_it(app, temp_db):
    """Đang ở tháng 05 mà chuyển sang "theo quý" thì ra quý 2, không nhảy đi."""
    from app.period import PeriodScope

    screen = _screen()

    _pick_scope(screen, PeriodScope.MONTH, 5)
    _pick_scope(screen, PeriodScope.QUARTER)

    assert screen._closing_period() == Period(year=2026, quarter=2)


def test_year_scope_disables_the_slot_and_covers_the_whole_year(app, temp_db):
    from app.period import PeriodScope

    screen = _screen()

    _pick_scope(screen, PeriodScope.YEAR)

    assert not screen._slot.isEnabled()
    assert screen._closing_period() == Period(year=2026)


def test_preview_follows_the_chosen_scope(app, temp_db):
    """Phát sinh tháng 06 chỉ hiện khi kỳ kết chuyển bao tháng đó."""
    from app.period import PeriodScope

    screen = _screen()
    _post(temp_db, "BH01", "131", "511", "50000000")    # ghi ngày 15/06/2026
    screen.on_activated()

    _pick_scope(screen, PeriodScope.QUARTER, 2)
    refs = {screen._preview.item(r, 0).text()
            for r in range(screen._preview.rowCount())}
    assert "KC-DT/2026-Q2" in refs

    _pick_scope(screen, PeriodScope.QUARTER, 3)
    assert screen._preview.rowCount() == 0
    assert "chưa có phát sinh" in screen._preview_note.text()

    _pick_scope(screen, PeriodScope.MONTH, 6)
    refs = {screen._preview.item(r, 0).text()
            for r in range(screen._preview.rowCount())}
    assert "KC-DT/2026-06" in refs


def test_posting_uses_the_chosen_scope_not_the_top_bar_period(app, temp_db):
    from app.period import PeriodScope

    screen = _screen()                                  # thanh trên: cả năm 2026
    _post(temp_db, "BH01", "131", "511", "50000000")
    _post(temp_db, "QL01", "642", "111", "20000000")
    screen.on_activated()

    _pick_scope(screen, PeriodScope.QUARTER, 2)
    period = screen._closing_period()
    created = screen._result_service().post(period.date_from, period.date_to)

    assert {e.ref for e in created} >= {"KC-DT/2026-Q2", "KC-CP/2026-Q2"}
    assert all(e.entry_date == date(2026, 6, 30) for e in created)
