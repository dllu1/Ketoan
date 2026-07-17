"""DashboardService characterization tests — pure aggregation, no Qt.

Locks the ledger→KPI/trend/expense/cash math so the single-pass aggregation
refactor stays behaviour-identical.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.models.journal import EntryStatus, JournalEntry, JournalLine

_Z = Decimal("0")
_M = Decimal("1000000")


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


def _entry(ref, day, lines, status=EntryStatus.POSTED):
    return JournalEntry(
        ref=ref, entry_date=day, description=f"CT {ref}", status=status,
        lines=[JournalLine(account_code=c, debit=d, credit=cr) for c, d, cr in lines],
    )


@pytest.fixture
def dashboard(in_memory_db):
    from data.repositories.account_repo import AccountRepository
    from data.repositories.invoice_repo import InvoiceRepository
    from data.repositories.journal_repo import JournalRepository
    from data.repositories.partner_repo import PartnerRepository
    from domain.services.dashboard_service import DashboardService
    from domain.services.journal_service import JournalService

    js = JournalService(JournalRepository(in_memory_db))
    js.create(_entry("OPEN", date(2025, 12, 20), [("111", 200 * _M, _Z), ("411", _Z, 200 * _M)]))
    js.create(_entry("BH01", date(2026, 1, 15), [("111", 100 * _M, _Z), ("511", _Z, 100 * _M)]))
    js.create(_entry("BH02", date(2026, 2, 20), [("131", 50 * _M, _Z), ("511", _Z, 50 * _M)]))
    js.create(_entry("GV01", date(2026, 2, 10), [("632", 60 * _M, _Z), ("156", _Z, 60 * _M)]))
    js.create(_entry("CP01", date(2026, 3, 5), [("642", 5 * _M, _Z), ("111", _Z, 5 * _M)]))
    js.create(_entry("CP02", date(2026, 3, 8), [("641", 3 * _M, _Z), ("112", _Z, 3 * _M)]))
    js.create(_entry("MUA1", date(2026, 1, 9), [("156", 40 * _M, _Z), ("331", _Z, 40 * _M)]))
    js.create(_entry("DRAFT", date(2026, 2, 1), [("111", 9 * _M, _Z), ("511", _Z, 9 * _M)],
                     status=EntryStatus.DRAFT))

    return DashboardService(
        JournalRepository(in_memory_db), AccountRepository(in_memory_db),
        InvoiceRepository(in_memory_db), PartnerRepository(in_memory_db),
        today=date(2026, 3, 31),
    ).build()


def test_period_and_data_flag(dashboard):
    assert dashboard.has_data is True
    assert dashboard.period_label == "03/2026"


def test_kpi_values(dashboard):
    kpis = {k.label_en: k for k in dashboard.kpis}
    assert kpis["Revenue MTD"].value == _Z            # no revenue in ref month 03
    assert kpis["Gross profit"].value == _Z
    assert kpis["Receivables"].value == 50 * _M
    assert kpis["Payables"].value == 40 * _M
    assert kpis["Cash & equiv."].value == 292 * _M    # 200+100-5-3 = 292
    assert kpis["Inventory"].value == -20 * _M        # 40 in - 60 out


def test_cash_kpi_running_spark(dashboard):
    cash = {k.label_en: k for k in dashboard.kpis}["Cash & equiv."]
    # Running month-end balance across the trailing 12 months.
    assert [Decimal(str(x)) for x in cash.spark[-4:]] == [
        200 * _M, 300 * _M, 300 * _M, 292 * _M
    ]


def test_trend_flows(dashboard):
    by_label = {t.label: t for t in dashboard.trend}
    assert by_label["01/26"].revenue == 100 * _M
    assert by_label["02/26"].revenue == 50 * _M
    assert by_label["02/26"].cost == 60 * _M
    assert by_label["03/26"].opex == 8 * _M           # 642 + 641


def test_expense_mix(dashboard):
    mix = [(s.label_en, s.amount) for s in dashboard.expense_mix]
    assert mix == [("632", 60 * _M), ("642", 5 * _M), ("641", 3 * _M)]
    assert dashboard.expense_total == 68 * _M


def test_cash_positions(dashboard):
    positions = [(c.code, c.amount) for c in dashboard.cash_positions]
    assert positions == [("111", 295 * _M), ("112", -3 * _M)]
