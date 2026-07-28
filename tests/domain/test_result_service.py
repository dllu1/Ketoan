"""Kết chuyển 911 — xác định kết quả kinh doanh (sổ tay Hưng Phát, mục V)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

Q4_FROM = date(2025, 10, 1)
Q4_TO = date(2025, 12, 31)


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


def _services(conn):
    from data.repositories.account_repo import AccountRepository
    from data.repositories.journal_repo import JournalRepository
    from domain.services.journal_service import JournalService
    from domain.services.result_service import ResultService

    journal = JournalService(JournalRepository(conn))
    return journal, ResultService(journal, AccountRepository(conn))


def _entry(journal, ref, debit_account, credit_account, amount, when=None):
    from domain.models.journal import EntryStatus, JournalEntry, JournalLine

    journal.create(JournalEntry(
        ref=ref,
        entry_date=when or date(2025, 11, 15),
        status=EntryStatus.POSTED,
        lines=[
            JournalLine(account_code=debit_account, debit=Decimal(amount)),
            JournalLine(account_code=credit_account, credit=Decimal(amount)),
        ],
    ))


def _net_911(journal):
    """Số dư TK 911 sau kết chuyển — phải bằng 0."""
    total = Decimal("0")
    for entry in journal.list_all():
        for line in entry.lines:
            if line.account_code == "911":
                total += line.debit - line.credit
    return total


def test_post_transfers_revenue_and_expense_then_profit(in_memory_db):
    journal, results = _services(in_memory_db)
    _entry(journal, "BH01", "131", "511", "100000000")   # doanh thu bán hàng
    _entry(journal, "GV01", "632", "155", "60000000")    # giá vốn
    _entry(journal, "QL01", "642", "111", "10000000")    # chi phí quản lý

    created = results.post(Q4_FROM, Q4_TO)

    assert [e.ref for e in created] == [
        "KC-DT/2025-Q4", "KC-CP/2025-Q4", "KC-LN/2025-Q4",
    ]
    assert all(e.is_balanced for e in created)

    # Doanh thu: Nợ 511 100tr / Có 911 100tr
    revenue = journal.find_by_ref("KC-DT/2025-Q4")
    assert {(ln.account_code, ln.debit, ln.credit) for ln in revenue.lines} == {
        ("511", Decimal("100000000"), Decimal("0")),
        ("911", Decimal("0"), Decimal("100000000")),
    }
    # Chi phí: Nợ 911 70tr / Có 632 60tr + Có 642 10tr
    expense = journal.find_by_ref("KC-CP/2025-Q4")
    assert {(ln.account_code, ln.debit, ln.credit) for ln in expense.lines} == {
        ("911", Decimal("70000000"), Decimal("0")),
        ("632", Decimal("0"), Decimal("60000000")),
        ("642", Decimal("0"), Decimal("10000000")),
    }
    # Lãi 30tr: Nợ 911 / Có 4212
    profit = journal.find_by_ref("KC-LN/2025-Q4")
    assert {(ln.account_code, ln.debit, ln.credit) for ln in profit.lines} == {
        ("911", Decimal("30000000"), Decimal("0")),
        ("4212", Decimal("0"), Decimal("30000000")),
    }
    # 911 là tài khoản trung gian — sau kết chuyển phải sạch.
    assert _net_911(journal) == Decimal("0")


def test_loss_reverses_the_result_entry(in_memory_db):
    journal, results = _services(in_memory_db)
    _entry(journal, "BH01", "131", "511", "40000000")
    _entry(journal, "GV01", "632", "155", "100000000")

    results.post(Q4_FROM, Q4_TO)

    # Lỗ 60tr: Nợ 4212 / Có 911 (ngược với trường hợp lãi).
    loss = journal.find_by_ref("KC-LN/2025-Q4")
    assert {(ln.account_code, ln.debit, ln.credit) for ln in loss.lines} == {
        ("4212", Decimal("60000000"), Decimal("0")),
        ("911", Decimal("0"), Decimal("60000000")),
    }
    assert _net_911(journal) == Decimal("0")


def test_posting_twice_replaces_instead_of_doubling(in_memory_db):
    journal, results = _services(in_memory_db)
    _entry(journal, "BH01", "131", "511", "100000000")
    _entry(journal, "GV01", "632", "155", "60000000")

    results.post(Q4_FROM, Q4_TO)
    results.post(Q4_FROM, Q4_TO)

    refs = [e.ref for e in journal.list_all() if e.ref.startswith("KC-")]
    assert sorted(refs) == ["KC-CP/2025-Q4", "KC-DT/2025-Q4", "KC-LN/2025-Q4"]
    profit = journal.find_by_ref("KC-LN/2025-Q4")
    # Vẫn đúng 40tr chứ không nhân đôi thành 80tr.
    assert max(ln.debit for ln in profit.lines) == Decimal("40000000")
    assert _net_911(journal) == Decimal("0")


def test_only_entries_inside_the_period_are_transferred(in_memory_db):
    journal, results = _services(in_memory_db)
    _entry(journal, "BH-Q4", "131", "511", "100000000", when=date(2025, 11, 15))
    _entry(journal, "BH-Q3", "131", "511", "999000000", when=date(2025, 8, 15))

    plan = results.plan(Q4_FROM, Q4_TO)
    assert plan.total_revenue == Decimal("100000000")


def test_sub_accounts_roll_up_to_their_parent_group(in_memory_db):
    """5111 vẫn là doanh thu, 6421 vẫn là chi phí quản lý."""
    journal, results = _services(in_memory_db)
    _entry(journal, "BH01", "131", "5111", "80000000")
    _entry(journal, "QL01", "6421", "111", "20000000")

    plan = results.plan(Q4_FROM, Q4_TO)
    assert plan.total_revenue == Decimal("80000000")
    assert plan.total_expense == Decimal("20000000")
    assert plan.profit == Decimal("60000000")
    assert plan.is_profit


def test_sales_returns_reduce_revenue(in_memory_db):
    """Ghi Nợ 511 (giảm trừ doanh thu) phải trừ ra chứ không cộng thêm."""
    journal, results = _services(in_memory_db)
    _entry(journal, "BH01", "131", "511", "100000000")
    _entry(journal, "TL01", "511", "131", "10000000")   # hàng bán bị trả lại

    plan = results.plan(Q4_FROM, Q4_TO)
    assert plan.total_revenue == Decimal("90000000")


def test_post_without_any_revenue_or_expense_is_rejected(in_memory_db):
    from domain.services.result_service import ResultError

    journal, results = _services(in_memory_db)
    _entry(journal, "TM01", "111", "112", "5000000")   # chỉ chuyển tiền

    with pytest.raises(ResultError, match="chưa có phát sinh"):
        results.post(Q4_FROM, Q4_TO)


def test_unpost_removes_the_transfer_entries(in_memory_db):
    journal, results = _services(in_memory_db)
    _entry(journal, "BH01", "131", "511", "100000000")
    results.post(Q4_FROM, Q4_TO)
    assert results.is_posted(Q4_FROM, Q4_TO)

    results.unpost(Q4_FROM, Q4_TO)

    assert not results.is_posted(Q4_FROM, Q4_TO)
    assert [e.ref for e in journal.list_all() if e.ref.startswith("KC-")] == []
