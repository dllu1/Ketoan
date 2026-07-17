"""ReportService tests — pure aggregation over the posted journal, no Qt."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.models.journal import EntryStatus, JournalEntry, JournalLine
from domain.models.report import ReportPeriod


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


def _journal(conn):
    from data.repositories.journal_repo import JournalRepository
    from domain.services.journal_service import JournalService

    return JournalService(JournalRepository(conn))


def _report(conn):
    from data.repositories.account_repo import AccountRepository
    from data.repositories.journal_repo import JournalRepository
    from domain.services.report_service import ReportService

    return ReportService(JournalRepository(conn), AccountRepository(conn))


def _entry(ref, day, lines, status=EntryStatus.POSTED):
    return JournalEntry(
        ref=ref,
        entry_date=day,
        description=f"CT {ref}",
        status=status,
        lines=[JournalLine(account_code=c, debit=d, credit=cr) for c, d, cr in lines],
    )


_Z = Decimal("0")
_M = Decimal("1000000")


@pytest.fixture
def seeded(in_memory_db):
    """A small but realistic ledger spanning before/within/after the period."""
    journal = _journal(in_memory_db)
    # Opening capital, before the period.
    journal.create(_entry("OPEN", date(2025, 12, 20),
                          [("111", 200 * _M, _Z), ("411", _Z, 200 * _M)]))
    # In-period sale, COGS, and a cash expense.
    journal.create(_entry("BH01", date(2026, 1, 15),
                          [("111", 100 * _M, _Z), ("511", _Z, 100 * _M)]))
    journal.create(_entry("GV01", date(2026, 2, 10),
                          [("632", 60 * _M, _Z), ("156", _Z, 60 * _M)]))
    journal.create(_entry("CP01", date(2026, 3, 5),
                          [("642", 5 * _M, _Z), ("111", _Z, 5 * _M)]))
    # A draft (must be ignored) and an out-of-range posting (after the period).
    journal.create(_entry("DRAFT", date(2026, 2, 1),
                          [("111", 9 * _M, _Z), ("511", _Z, 9 * _M)],
                          status=EntryStatus.DRAFT))
    journal.create(_entry("BH99", date(2026, 4, 20),
                          [("111", 7 * _M, _Z), ("511", _Z, 7 * _M)]))
    return in_memory_db


_PERIOD = ReportPeriod(start=date(2026, 1, 1), end=date(2026, 3, 31))


def test_general_journal_excludes_drafts_and_out_of_range(seeded):
    report = _report(seeded).general_journal(_PERIOD)
    refs = {r.ref for r in report.rows}
    assert refs == {"BH01", "GV01", "CP01"}
    assert report.is_balanced
    assert report.total_debit == 165 * _M


def test_trial_balance_columns_self_balance(seeded):
    tb = _report(seeded).trial_balance(_PERIOD)
    assert tb.is_balanced
    assert tb.total_opening_debit == 200 * _M
    assert tb.total_period_debit == 165 * _M
    assert tb.total_closing_debit == 360 * _M


def test_trial_balance_account_111_running_balance(seeded):
    tb = _report(seeded).trial_balance(_PERIOD)
    row = next(r for r in tb.rows if r.code == "111")
    assert row.opening_debit == 200 * _M
    assert row.period_debit == 100 * _M
    assert row.period_credit == 5 * _M
    assert row.closing_debit == 295 * _M


def _debt_entry(ref, day, lines):
    """Entry whose lines carry (account, debit, credit, partner_code)."""
    return JournalEntry(
        ref=ref, entry_date=day, description=f"CT {ref}",
        status=EntryStatus.POSTED,
        lines=[JournalLine(account_code=a, debit=d, credit=c, partner_code=p)
               for a, d, c, p in lines],
    )


@pytest.fixture
def debt_seeded(in_memory_db):
    """Two customers (131) and one supplier (331), spanning before/within period."""
    journal = _journal(in_memory_db)
    # Trước kỳ: KH-A còn nợ đầu kỳ 30tr (bán chịu).
    journal.create(_debt_entry("BH-A0", date(2025, 12, 10),
                               [("131", 30 * _M, _Z, "KH-A"), ("511", _Z, 30 * _M, "")]))
    # Trong kỳ: bán chịu thêm cho A và B, A trả 20tr.
    journal.create(_debt_entry("BH-A1", date(2026, 1, 20),
                               [("131", 50 * _M, _Z, "KH-A"), ("511", _Z, 50 * _M, "")]))
    journal.create(_debt_entry("BH-B1", date(2026, 2, 5),
                               [("131", 40 * _M, _Z, "KH-B"), ("511", _Z, 40 * _M, "")]))
    journal.create(_debt_entry("TT-A1", date(2026, 3, 1),
                               [("111", 20 * _M, _Z, ""), ("131", _Z, 20 * _M, "KH-A")]))
    # Mua chịu của NCC-X 70tr trong kỳ (331 credit).
    journal.create(_debt_entry("MH-X1", date(2026, 2, 15),
                               [("156", 70 * _M, _Z, ""), ("331", _Z, 70 * _M, "NCC-X")]))
    return in_memory_db


def test_debt_summary_receivables_per_partner(debt_seeded):
    report = _report(debt_seeded).debt_summary(
        _PERIOD, "131", account_label="131 — Phải thu", debit_positive=True
    )
    rows = {r.partner_code: r for r in report.rows}
    assert set(rows) == {"KH-A", "KH-B"}
    # KH-A: đầu 30, PS Nợ 50, PS Có 20 → cuối 60.
    assert rows["KH-A"].opening == 30 * _M
    assert rows["KH-A"].debit == 50 * _M
    assert rows["KH-A"].credit == 20 * _M
    assert rows["KH-A"].closing == 60 * _M
    # KH-B: không có đầu kỳ, phát sinh 40 trong kỳ.
    assert rows["KH-B"].opening == _Z
    assert rows["KH-B"].closing == 40 * _M
    assert report.total_closing == 100 * _M


def test_debt_summary_payables_side(debt_seeded):
    report = _report(debt_seeded).debt_summary(
        _PERIOD, "331", account_label="331 — Phải trả", debit_positive=False
    )
    rows = {r.partner_code: r for r in report.rows}
    assert set(rows) == {"NCC-X"}
    # 331 credit-heavy: net (Nợ − Có) = −70; builder flips sign to show +70 phải trả.
    assert rows["NCC-X"].closing == -70 * _M
    assert report.total_credit == 70 * _M


def test_debt_summary_excludes_untagged_lines(debt_seeded):
    report = _report(debt_seeded).debt_summary(_PERIOD, "131")
    # Untagged 511 lines never appear; only 131 partner rows do.
    assert all(r.partner_code in {"KH-A", "KH-B"} for r in report.rows)


def test_general_ledger_account_111_running_balance(seeded):
    gl = _report(seeded).general_ledger(_PERIOD)
    acc = next(a for a in gl.accounts if a.code == "111")
    assert acc.opening_balance == 200 * _M
    # Only in-range, posted lines touching 111 appear (BH01 debit, CP01 credit).
    assert [(r.ref, r.debit, r.credit) for r in acc.rows] == [
        ("BH01", 100 * _M, _Z),
        ("CP01", _Z, 5 * _M),
    ]
    # Counter accounts (TK đối ứng) come from the opposite side of each entry.
    assert [r.counter_account for r in acc.rows] == ["511", "642"]
    # Running balance: 200M → +100M → −5M.
    assert [r.balance for r in acc.rows] == [300 * _M, 295 * _M]
    assert acc.total_debit == 100 * _M
    assert acc.total_credit == 5 * _M
    assert acc.closing_balance == 295 * _M


def test_general_ledger_full_ledger_is_balanced(seeded):
    gl = _report(seeded).general_ledger(_PERIOD)
    # 411 carries only an opening balance (no in-period movement) yet still shows.
    assert any(a.code == "411" and not a.rows for a in gl.accounts)
    # Double entry: signed closing balances across all accounts net to zero.
    assert gl.is_balanced


def test_general_ledger_single_account_filter(seeded):
    gl = _report(seeded).general_ledger(_PERIOD, account_code="511")
    assert [a.code for a in gl.accounts] == ["511"]
    acc = gl.accounts[0]
    assert acc.opening_balance == _Z
    assert acc.closing_balance == -100 * _M       # net credit account


def test_general_ledger_empty_when_account_has_no_activity(seeded):
    gl = _report(seeded).general_ledger(_PERIOD, account_code="999")
    assert gl.accounts == []


def test_income_statement_profit(seeded):
    pl = _report(seeded).income_statement(_PERIOD)
    assert pl.total_revenue == 100 * _M
    assert pl.total_expense == 65 * _M
    assert pl.profit_before_tax == 35 * _M


def test_balance_sheet_balances_with_period_result(seeded):
    bs = _report(seeded).balance_sheet(date(2026, 3, 31))
    assert bs.total_assets == 235 * _M
    assert bs.result_profit == 35 * _M
    assert bs.is_balanced


def test_cash_flow_direct_movements(seeded):
    cf = _report(seeded).cash_flow(_PERIOD)
    assert cf.opening_balance == 200 * _M
    assert cf.total_inflow == 100 * _M
    assert cf.total_outflow == 5 * _M
    assert cf.closing_balance == 295 * _M


def test_empty_ledger_reports_are_balanced(in_memory_db):
    report = _report(in_memory_db)
    assert report.trial_balance(_PERIOD).is_balanced
    assert report.general_journal(_PERIOD).rows == []
    assert report.balance_sheet(date(2026, 3, 31)).is_balanced


def test_declared_opening_appears_when_prior_period_empty(in_memory_db):
    """Số dư đầu kỳ feeds the trial balance even with no prior-year postings."""
    from data.repositories.item_repo import ItemRepository
    from domain.models.item import Item, ItemCategory
    from domain.models.opening import OpeningBalance
    from domain.services.opening_service import OpeningBalanceService

    ItemRepository(in_memory_db).insert(
        Item(code="NVL01", name="Thép", category=ItemCategory.MATERIAL, unit="kg")
    )
    OpeningBalanceService().save(2026, [
        OpeningBalance(fiscal_year=2026, account_code="152", item_code="NVL01",
                       opening_qty=Decimal("100"), opening_value=5 * _M),
    ])

    tb = _report(in_memory_db).trial_balance(_PERIOD)
    row = next(r for r in tb.rows if r.code == "152")
    assert row.opening_debit == 5 * _M
    assert row.closing_debit == 5 * _M
