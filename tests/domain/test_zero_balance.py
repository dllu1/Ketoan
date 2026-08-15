"""Tài khoản không có số dư cuối kỳ: danh sách khai được + kiểm tra đúng.

Đây là lưới an toàn của bước kết chuyển: sau khi chạy kết chuyển, 511/632/911…
phải hết số dư. Còn dư là dấu hiệu thiếu quy tắc hoặc khai sai chiều Nợ/Có.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

YEAR_FROM = date(2026, 1, 1)
YEAR_TO = date(2026, 12, 31)


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
    from data.repositories.settings_repo import SettingsRepository
    from data.repositories.transfer_rule_repo import TransferRuleRepository
    from data.repositories.zero_balance_repo import ZeroBalanceRepository
    from domain.services.journal_service import JournalService
    from domain.services.result_service import ResultService
    from domain.services.transfer_rule_service import TransferRuleService
    from domain.services.zero_balance_service import ZeroBalanceService

    journal = JournalService(JournalRepository(conn))
    rules = TransferRuleService(
        TransferRuleRepository(conn), SettingsRepository(conn)
    )
    results = ResultService(journal, AccountRepository(conn), rules=rules)
    zero = ZeroBalanceService(
        ZeroBalanceRepository(conn), JournalRepository(conn),
        AccountRepository(conn), SettingsRepository(conn),
    )
    return journal, results, zero


def _entry(journal, ref, debit_account, credit_account, amount):
    from domain.models.journal import EntryStatus, JournalEntry, JournalLine

    journal.create(JournalEntry(
        ref=ref,
        entry_date=date(2026, 11, 15),
        status=EntryStatus.POSTED,
        lines=[
            JournalLine(account_code=debit_account, debit=Decimal(amount)),
            JournalLine(account_code=credit_account, credit=Decimal(amount)),
        ],
    ))


def _codes(report):
    return [issue.account_code for issue in report.issues]


# ----- bộ mặc định -----------------------------------------------------------


def test_defaults_are_seeded_on_first_use(in_memory_db):
    _journal, _results, zero = _services(in_memory_db)

    codes = {r.account_code for r in zero.list_rules()}

    assert {"511", "632", "641", "642", "911"} <= codes
    # Hàng tồn kho và dở dang ĐƯỢC phép còn dư — không nằm trong bộ mặc định.
    assert codes.isdisjoint({"154", "155", "156", "131", "331"})


# ----- kiểm tra --------------------------------------------------------------


def test_unclosed_revenue_is_reported(in_memory_db):
    """Có doanh thu mà chưa kết chuyển → 511 bị nêu là còn số dư Có."""
    journal, _results, zero = _services(in_memory_db)
    _entry(journal, "BH01", "131", "511", "50000000")

    report = zero.check(YEAR_TO)

    assert not report.is_clean
    assert _codes(report) == ["511"]
    issue = report.issues[0]
    assert issue.balance == Decimal("-50000000")   # net Nợ − Có → dư Có
    assert issue.credit_balance == Decimal("50000000")
    assert issue.debit_balance == Decimal("0")
    assert issue.side_label == "Dư Có"


def test_check_is_clean_after_transfer(in_memory_db):
    """Kết chuyển xong thì 511/642/911 đều sạch."""
    journal, results, zero = _services(in_memory_db)
    _entry(journal, "BH01", "131", "511", "50000000")
    _entry(journal, "QL01", "642", "111", "20000000")

    results.post(YEAR_FROM, YEAR_TO)
    report = zero.check(YEAR_TO)

    assert report.is_clean, _codes(report)
    assert report.total == Decimal("0")
    assert report.checked_accounts > 0


def test_missing_transfer_rule_shows_up_as_residual_balance(in_memory_db):
    """Bỏ 642 khỏi quy tắc kết chuyển → sau kết chuyển 642 vẫn treo dư Nợ."""
    from domain.models.transfer_rule import TransferDirection, TransferRule

    journal, results, zero = _services(in_memory_db)
    results._rules.save_rules([
        TransferRule(source_account="511", target_account="911",
                     direction=TransferDirection.DEBIT_SOURCE,
                     group_ref="KC-DT", sort_order=10),
    ])
    _entry(journal, "BH01", "131", "511", "50000000")
    _entry(journal, "QL01", "642", "111", "20000000")

    results.post(YEAR_FROM, YEAR_TO)
    report = zero.check(YEAR_TO)

    assert _codes(report) == ["642"]
    assert report.issues[0].debit_balance == Decimal("20000000")


def test_entry_posted_after_the_transfer_is_caught(in_memory_db):
    """Ghi thêm bút toán sau khi đã kết chuyển → 511 lệch, phải báo."""
    journal, results, zero = _services(in_memory_db)
    _entry(journal, "BH01", "131", "511", "50000000")
    results.post(YEAR_FROM, YEAR_TO)
    assert zero.check(YEAR_TO).is_clean

    _entry(journal, "BH02", "131", "511", "7000000")   # quên kết chuyển lại

    assert _codes(zero.check(YEAR_TO)) == ["511"]


def test_tolerance_absorbs_rounding_difference(in_memory_db):
    """Dung sai bỏ qua lệch làm tròn nhưng vẫn bắt lệch lớn hơn."""
    from domain.models.zero_balance import ZeroBalanceRule

    journal, _results, zero = _services(in_memory_db)
    zero.save_rules([
        ZeroBalanceRule(account_code="632", tolerance=Decimal("10"), sort_order=10),
    ])
    _entry(journal, "GV01", "632", "155", "9")

    assert zero.check(YEAR_TO).is_clean

    _entry(journal, "GV02", "632", "155", "5")   # tổng 14 > dung sai 10
    assert _codes(zero.check(YEAR_TO)) == ["632"]


def test_sub_accounts_follow_the_parent_unless_declared(in_memory_db):
    """5111 theo quy tắc của 511; khai riêng 5111 thì dùng dung sai của nó."""
    from domain.models.zero_balance import ZeroBalanceRule

    journal, _results, zero = _services(in_memory_db)
    zero.save_rules([
        ZeroBalanceRule(account_code="511", tolerance=Decimal("0"), sort_order=10),
    ])
    _entry(journal, "BH01", "131", "5111", "1000")
    assert _codes(zero.check(YEAR_TO)) == ["5111"]

    zero.save_rules([
        ZeroBalanceRule(account_code="511", tolerance=Decimal("0"), sort_order=10),
        ZeroBalanceRule(account_code="5111", tolerance=Decimal("5000"),
                        sort_order=20),
    ])
    assert zero.check(YEAR_TO).is_clean


def test_exact_scope_ignores_children(in_memory_db):
    from domain.models.zero_balance import ZeroBalanceRule

    journal, _results, zero = _services(in_memory_db)
    zero.save_rules([
        ZeroBalanceRule(account_code="511", include_children=False, sort_order=10),
    ])
    _entry(journal, "BH01", "131", "5111", "1000")

    assert zero.check(YEAR_TO).is_clean


def test_clearing_the_list_disables_the_check(in_memory_db):
    """Xóa hết dòng rồi lưu = tắt kiểm tra; nạp lại không tự đổ mặc định về."""
    journal, _results, zero = _services(in_memory_db)
    _entry(journal, "BH01", "131", "511", "50000000")
    zero.save_rules([])

    report = zero.check(YEAR_TO)

    assert report.checked_accounts == 0
    assert report.is_clean
    assert zero.list_rules() == []


def test_inactive_rule_is_skipped(in_memory_db):
    from domain.models.zero_balance import ZeroBalanceRule

    journal, _results, zero = _services(in_memory_db)
    zero.save_rules([
        ZeroBalanceRule(account_code="511", active=False, sort_order=10),
    ])
    _entry(journal, "BH01", "131", "511", "50000000")

    assert zero.check(YEAR_TO).is_clean


# ----- kiểm tra đầu vào ------------------------------------------------------


def test_duplicate_and_blank_rows_are_rejected(in_memory_db):
    from domain.models.zero_balance import ZeroBalanceRule
    from domain.services.zero_balance_service import ZeroBalanceError

    _journal, _results, zero = _services(in_memory_db)

    with pytest.raises(ZeroBalanceError, match="mã tài khoản"):
        zero.save_rules([ZeroBalanceRule(account_code="  ")])
    with pytest.raises(ZeroBalanceError, match="trùng hai lần"):
        zero.save_rules([
            ZeroBalanceRule(account_code="511"),
            ZeroBalanceRule(account_code="511"),
        ])
    with pytest.raises(ZeroBalanceError, match="không được âm"):
        zero.save_rules([
            ZeroBalanceRule(account_code="511", tolerance=Decimal("-1")),
        ])


@pytest.mark.parametrize("text, expected", [
    ("", "0"),
    ("  ", "0"),
    ("100", "100"),
    ("1.000", "1000"),
    ("1,000", "1000"),
    (" 2 000 ", "2000"),
])
def test_parse_tolerance_accepts_typed_thousands(text, expected):
    from domain.services.zero_balance_service import parse_tolerance

    assert parse_tolerance(text) == Decimal(expected)


def test_parse_tolerance_rejects_nonsense():
    from domain.services.zero_balance_service import (
        ZeroBalanceError,
        parse_tolerance,
    )

    with pytest.raises(ZeroBalanceError, match="không phải là số"):
        parse_tolerance("abc")
    with pytest.raises(ZeroBalanceError, match="không được âm"):
        parse_tolerance("-5")
