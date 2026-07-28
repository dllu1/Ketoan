"""Chi phí trả trước (TK 242) — phân bổ dần theo tháng (sổ tay mục I.3.d)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest


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


def _service(conn, *, with_journal=True):
    from data.repositories.account_repo import AccountRepository
    from data.repositories.journal_repo import JournalRepository
    from data.repositories.prepaid_repo import PrepaidRepository
    from domain.services.journal_service import JournalService
    from domain.services.prepaid_service import PrepaidService

    journal = JournalService(JournalRepository(conn)) if with_journal else None
    return PrepaidService(
        PrepaidRepository(conn), journal, AccountRepository(conn)
    ), journal


def _prepaid(code="CPTT01", total="36000000", months=12, year=2025, month=10,
             expense="642"):
    from domain.models.prepaid import PrepaidExpense

    return PrepaidExpense(
        code=code, name="Bảo hiểm xe 1 năm",
        total_amount=Decimal(total), months=months,
        start_year=year, start_month=month, expense_account=expense,
    )


# ----- lịch phân bổ --------------------------------------------------------


def test_monthly_amount_divides_evenly():
    p = _prepaid()
    assert p.monthly_amount == Decimal("3000000")
    assert p.amount_for(2025, 10) == Decimal("3000000")
    assert p.amount_for(2026, 9) == Decimal("3000000")   # tháng thứ 12


def test_months_outside_the_window_get_nothing():
    p = _prepaid()
    assert p.amount_for(2025, 9) == Decimal("0")     # trước khi bắt đầu
    assert p.amount_for(2026, 10) == Decimal("0")    # sau khi kết thúc


def test_last_month_absorbs_the_rounding_remainder():
    """10.000.000 / 3 tháng: 3.333.333 + 3.333.333 + 3.333.334 = đúng tổng."""
    p = _prepaid(total="10000000", months=3, year=2025, month=1)
    amounts = [p.amount_for(2025, m) for m in (1, 2, 3)]
    assert amounts == [Decimal("3333333"), Decimal("3333333"), Decimal("3333334")]
    assert sum(amounts) == Decimal("10000000")


def test_schedule_covers_every_month_and_sums_to_total(in_memory_db):
    service, _ = _service(in_memory_db)
    p = _prepaid(total="10000000", months=3, year=2025, month=11)

    rows = service.schedule(p)

    assert [r.label for r in rows] == ["T11/2025", "T12/2025", "T01/2026"]
    assert sum(r.amount for r in rows) == Decimal("10000000")
    # Dòng cuối: đã phân bổ hết, còn lại 0.
    assert rows[-1].allocated == Decimal("10000000")
    assert rows[-1].remaining == Decimal("0")


def test_remaining_tracks_the_unallocated_balance():
    p = _prepaid()   # 36tr / 12 tháng từ 10/2025
    assert p.allocated_through(2025, 12) == Decimal("9000000")   # 3 tháng
    assert p.remaining_after(2025, 12) == Decimal("27000000")


# ----- ghi sổ --------------------------------------------------------------


def test_post_monthly_creates_debit_expense_credit_242(in_memory_db):
    service, _ = _service(in_memory_db)
    service.save(_prepaid())

    entry = service.post_monthly(2025, 10)

    assert entry is not None
    assert entry.ref == "PBCP-202510"
    assert entry.entry_date == date(2025, 10, 31)
    assert entry.is_balanced
    assert {(ln.account_code, ln.debit, ln.credit) for ln in entry.lines} == {
        ("642", Decimal("3000000"), Decimal("0")),
        ("242", Decimal("0"), Decimal("3000000")),
    }


def test_post_monthly_groups_several_prepaids_by_account(in_memory_db):
    service, _ = _service(in_memory_db)
    service.save(_prepaid("CPTT01", "12000000", 12, 2025, 1, expense="642"))
    service.save(_prepaid("CPTT02", "24000000", 12, 2025, 1, expense="642"))
    service.save(_prepaid("CPTT03", "12000000", 12, 2025, 1, expense="641"))

    entry = service.post_monthly(2025, 5)

    by_account = {ln.account_code: (ln.debit, ln.credit) for ln in entry.lines}
    assert by_account["642"][0] == Decimal("3000000")   # 1tr + 2tr
    assert by_account["641"][0] == Decimal("1000000")
    assert by_account["242"][1] == Decimal("4000000")
    assert entry.is_balanced


def test_posting_the_same_month_twice_replaces_the_entry(in_memory_db):
    service, journal = _service(in_memory_db)
    service.save(_prepaid())

    service.post_monthly(2025, 10)
    service.post_monthly(2025, 10)

    refs = [e.ref for e in journal.list_all() if e.ref.startswith("PBCP-")]
    assert refs == ["PBCP-202510"]


def test_month_with_nothing_due_posts_no_entry(in_memory_db):
    service, _ = _service(in_memory_db)
    service.save(_prepaid())   # bắt đầu 10/2025

    assert service.post_monthly(2025, 9) is None


def test_full_schedule_posts_exactly_the_total(in_memory_db):
    """Chạy hết 3 tháng thì tổng ghi sổ đúng bằng số tiền ban đầu."""
    service, _ = _service(in_memory_db)
    service.save(_prepaid(total="10000000", months=3, year=2025, month=1))

    total = Decimal("0")
    for month in (1, 2, 3):
        entry = service.post_monthly(2025, month)
        total += sum(ln.credit for ln in entry.lines)
    assert total == Decimal("10000000")


# ----- kiểm tra đầu vào ----------------------------------------------------


@pytest.mark.parametrize("kwargs, message", [
    ({"total": "0"}, "lớn hơn 0"),
    ({"months": 0}, "số tháng"),
    ({"month": 13}, "từ 1 đến 12"),
])
def test_invalid_input_is_rejected(in_memory_db, kwargs, message):
    from domain.services.prepaid_service import PrepaidValidationError

    service, _ = _service(in_memory_db)
    with pytest.raises(PrepaidValidationError, match="(?i)" + message):
        service.save(_prepaid(**kwargs))


def test_duplicate_code_is_rejected(in_memory_db):
    from domain.services.prepaid_service import PrepaidValidationError

    service, _ = _service(in_memory_db)
    service.save(_prepaid())
    with pytest.raises(PrepaidValidationError, match="đã tồn tại"):
        service.save(_prepaid())


def test_save_reload_roundtrip(in_memory_db):
    service, _ = _service(in_memory_db)
    service.save(_prepaid())

    loaded = service.list_all()[0]
    assert loaded.code == "CPTT01"
    assert loaded.total_amount == Decimal("36000000")
    assert loaded.months == 12
    assert loaded.expense_account == "642"
    assert loaded.asset_account == "242"
