"""Kết chuyển động: người dùng tự khai TK nguồn → TK đích và chiều Nợ/Có.

Trước đây danh sách doanh thu / chi phí nằm cứng trong ResultService. Nay nó là
bảng ``transfer_rule`` sửa được từ màn hình Kết chuyển; các test dưới đây chốt
rằng bộ mặc định giữ nguyên hành vi cũ, còn khi người dùng chỉnh thì bút toán đi
theo đúng cấu hình.
"""
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
    from data.repositories.settings_repo import SettingsRepository
    from data.repositories.transfer_rule_repo import TransferRuleRepository
    from domain.services.journal_service import JournalService
    from domain.services.result_service import ResultService
    from domain.services.transfer_rule_service import TransferRuleService

    journal = JournalService(JournalRepository(conn))
    rules = TransferRuleService(
        TransferRuleRepository(conn), SettingsRepository(conn)
    )
    results = ResultService(journal, AccountRepository(conn), rules=rules)
    return journal, rules, results


def _entry(journal, ref, debit_account, credit_account, amount):
    from domain.models.journal import EntryStatus, JournalEntry, JournalLine

    journal.create(JournalEntry(
        ref=ref,
        entry_date=date(2025, 11, 15),
        status=EntryStatus.POSTED,
        lines=[
            JournalLine(account_code=debit_account, debit=Decimal(amount)),
            JournalLine(account_code=credit_account, credit=Decimal(amount)),
        ],
    ))


def _sides(entry):
    return {(ln.account_code, ln.debit, ln.credit) for ln in entry.lines}


# ----- bộ mặc định -----------------------------------------------------------


def test_defaults_are_seeded_on_first_use(in_memory_db):
    _journal, rules, _results = _services(in_memory_db)

    seeded = rules.list_rules()

    assert {r.source_account for r in seeded} >= {"511", "515", "632", "642"}
    assert all(r.target_account == "911" for r in seeded)
    assert rules.result_account() == "911"
    assert rules.profit_account() == "4212"


# ----- người dùng đổi cấu hình ----------------------------------------------


def test_user_can_route_515_to_its_own_entry(in_memory_db):
    """VD trong yêu cầu: 515 kết chuyển sang **Có** 911, tách riêng số chứng từ."""
    from domain.models.transfer_rule import TransferDirection, TransferRule

    journal, rules, results = _services(in_memory_db)
    rules.save_rules([
        TransferRule(source_account="515", target_account="911",
                     direction=TransferDirection.DEBIT_SOURCE,
                     group_ref="KC-TC", sort_order=10),
        TransferRule(source_account="642", target_account="911",
                     direction=TransferDirection.CREDIT_SOURCE,
                     group_ref="KC-CP", sort_order=20),
    ])
    _entry(journal, "TC01", "112", "515", "5000000")     # lãi tiền gửi
    _entry(journal, "QL01", "642", "111", "2000000")

    results.post(Q4_FROM, Q4_TO)

    # 515 ghi Nợ, 911 ghi Có — đúng "kết chuyển 515 sang có của 911".
    assert _sides(journal.find_by_ref("KC-TC/2025-Q4")) == {
        ("515", Decimal("5000000"), Decimal("0")),
        ("911", Decimal("0"), Decimal("5000000")),
    }
    assert _sides(journal.find_by_ref("KC-CP/2025-Q4")) == {
        ("911", Decimal("2000000"), Decimal("0")),
        ("642", Decimal("0"), Decimal("2000000")),
    }
    # Lãi 3tr sang 4212.
    assert _sides(journal.find_by_ref("KC-LN/2025-Q4")) == {
        ("911", Decimal("3000000"), Decimal("0")),
        ("4212", Decimal("0"), Decimal("3000000")),
    }


def test_direction_can_be_reversed_by_the_user(in_memory_db):
    """Đảo chiều một quy tắc thì bút toán đảo theo, không cần sửa code."""
    from domain.models.transfer_rule import TransferDirection, TransferRule

    journal, rules, results = _services(in_memory_db)
    rules.save_rules([
        TransferRule(source_account="511", target_account="911",
                     direction=TransferDirection.CREDIT_SOURCE,   # cố ý ngược
                     group_ref="KC-DT", sort_order=10),
    ])
    _entry(journal, "BH01", "511", "131", "1000000")   # 511 dư Nợ

    results.post(Q4_FROM, Q4_TO)

    assert _sides(journal.find_by_ref("KC-DT/2025-Q4")) == {
        ("911", Decimal("1000000"), Decimal("0")),
        ("511", Decimal("0"), Decimal("1000000")),
    }


def test_target_account_is_not_limited_to_911(in_memory_db):
    """Kết chuyển sang tài khoản khác (vd: 631 → 632) chạy như một nhóm riêng."""
    from domain.models.transfer_rule import TransferDirection, TransferRule

    journal, rules, results = _services(in_memory_db)
    rules.save_rules([
        TransferRule(source_account="631", target_account="632",
                     direction=TransferDirection.CREDIT_SOURCE,
                     group_ref="KC-GT", sort_order=10),
        TransferRule(source_account="511", target_account="911",
                     direction=TransferDirection.DEBIT_SOURCE,
                     group_ref="KC-DT", sort_order=20),
    ])
    _entry(journal, "GT01", "631", "154", "4000000")
    _entry(journal, "BH01", "131", "511", "9000000")

    results.post(Q4_FROM, Q4_TO)

    assert _sides(journal.find_by_ref("KC-GT/2025-Q4")) == {
        ("632", Decimal("4000000"), Decimal("0")),
        ("631", Decimal("0"), Decimal("4000000")),
    }
    # 632 không có quy tắc nào nên KHÔNG bị kéo sang 911 — lãi chỉ tính 511.
    assert _sides(journal.find_by_ref("KC-LN/2025-Q4")) == {
        ("911", Decimal("9000000"), Decimal("0")),
        ("4212", Decimal("0"), Decimal("9000000")),
    }


def test_more_specific_rule_wins_over_the_parent(in_memory_db):
    """Khai 511 (gồm TK con) rồi khai riêng 5118 thì 5118 đi theo quy tắc riêng."""
    from domain.models.transfer_rule import TransferDirection, TransferRule

    journal, rules, results = _services(in_memory_db)
    rules.save_rules([
        TransferRule(source_account="511", target_account="911",
                     direction=TransferDirection.DEBIT_SOURCE,
                     group_ref="KC-DT", sort_order=10),
        TransferRule(source_account="5118", target_account="911",
                     direction=TransferDirection.DEBIT_SOURCE,
                     group_ref="KC-DTK", sort_order=20),
    ])
    _entry(journal, "BH01", "131", "5111", "6000000")
    _entry(journal, "BH02", "131", "5118", "1000000")

    results.post(Q4_FROM, Q4_TO)

    assert {ln.account_code for ln in journal.find_by_ref("KC-DT/2025-Q4").lines} \
        == {"5111", "911"}
    assert {ln.account_code for ln in journal.find_by_ref("KC-DTK/2025-Q4").lines} \
        == {"5118", "911"}


def test_result_and_profit_accounts_are_configurable(in_memory_db):
    """Đổi TK kết quả thì các quy tắc đang trỏ về TK cũ được chuyển theo."""
    journal, rules, results = _services(in_memory_db)
    assert rules.set_result_accounts("9111", "4211") > 0
    assert all(r.target_account == "9111" for r in rules.list_rules())
    _entry(journal, "BH01", "131", "511", "8000000")

    results.post(Q4_FROM, Q4_TO)

    assert _sides(journal.find_by_ref("KC-LN/2025-Q4")) == {
        ("9111", Decimal("8000000"), Decimal("0")),
        ("4211", Decimal("0"), Decimal("8000000")),
    }


def test_renaming_a_group_cleans_up_the_old_entry(in_memory_db):
    """Đổi số chứng từ của nhóm rồi chạy lại: bút toán cũ phải biến mất."""
    from domain.models.transfer_rule import TransferDirection, TransferRule

    journal, rules, results = _services(in_memory_db)
    _entry(journal, "BH01", "131", "511", "7000000")
    results.post(Q4_FROM, Q4_TO)
    assert journal.find_by_ref("KC-DT/2025-Q4") is not None

    rules.save_rules([
        TransferRule(source_account="511", target_account="911",
                     direction=TransferDirection.DEBIT_SOURCE,
                     group_ref="KC-DOANHTHU", sort_order=10),
    ])
    results.post(Q4_FROM, Q4_TO)

    assert journal.find_by_ref("KC-DT/2025-Q4") is None
    assert journal.find_by_ref("KC-DOANHTHU/2025-Q4") is not None


# ----- kiểm tra đầu vào ------------------------------------------------------


@pytest.mark.parametrize("source, target, group, message", [
    ("511", "511", "KC-DT", "không được trùng"),
    ("511", "911", "", "thiếu số chứng từ"),
    ("511", "911", "KC-GV", "kết chuyển giá vốn"),
    ("911", "4212", "KC-DT", "xác định kết quả"),
])
def test_invalid_rules_are_rejected(in_memory_db, source, target, group, message):
    from domain.models.transfer_rule import TransferRule
    from domain.services.transfer_rule_service import TransferRuleError

    _journal, rules, _results = _services(in_memory_db)

    with pytest.raises(TransferRuleError, match=message):
        rules.save_rules([
            TransferRule(source_account=source, target_account=target,
                         group_ref=group)
        ])


def test_duplicate_source_is_rejected(in_memory_db):
    from domain.models.transfer_rule import TransferRule
    from domain.services.transfer_rule_service import TransferRuleError

    _journal, rules, _results = _services(in_memory_db)

    with pytest.raises(TransferRuleError, match="trùng hai lần"):
        rules.save_rules([
            TransferRule(source_account="511", group_ref="KC-DT"),
            TransferRule(source_account="511", group_ref="KC-CP"),
        ])
