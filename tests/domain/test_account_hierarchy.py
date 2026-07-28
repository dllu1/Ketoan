"""Tài khoản tổng hợp (cha–con): helper thuần + validate + cộng gộp báo cáo."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.services import account_hierarchy as H


# --- helper thuần ---------------------------------------------------------


def test_aggregate_sums_children_into_parent():
    base = {"A": Decimal(10), "B": Decimal(20), "C": Decimal(30), "D": Decimal(5)}
    parents = {"A": "D", "B": "D", "C": "D"}
    agg = H.aggregate(base, parents)
    assert agg["D"] == Decimal(65)      # 5 riêng + 10 + 20 + 30
    assert agg["A"] == Decimal(10)      # lá giữ nguyên


def test_aggregate_multi_level():
    base = {"A": Decimal(10), "B": Decimal(20), "D": Decimal(0), "TONG": Decimal(0)}
    parents = {"A": "D", "B": "D", "D": "TONG"}
    agg = H.aggregate(base, parents)
    assert agg["D"] == Decimal(30)
    assert agg["TONG"] == Decimal(30)   # gộp qua nhiều cấp


def test_normalize_drops_self_unknown_and_cycles():
    parents = {"A": "A", "B": "GHOST", "C": "D", "D": "C"}
    clean = H.normalize_parents(parents, known={"A", "B", "C", "D"})
    assert "A" not in clean             # tự trỏ
    assert "B" not in clean             # cha không tồn tại
    # C<->D là vòng lặp: ít nhất một mắt xích bị cắt để không còn vòng
    assert not (clean.get("C") == "D" and clean.get("D") == "C")


def test_depth_and_descendants():
    parents = {"A": "D", "B": "D", "D": "TONG"}
    assert H.depth("A", parents) == 2
    assert H.depth("D", parents) == 1
    assert H.depth("TONG", parents) == 0
    assert H.descendants("TONG", parents) == {"D", "A", "B"}


# --- validate service -----------------------------------------------------


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


def _accounts(conn):
    from data.repositories.account_repo import AccountRepository
    from data.repositories.settings_repo import SettingsRepository
    from domain.services.account_service import AccountService

    return AccountService(AccountRepository(conn), SettingsRepository(conn))


def _acc(code, name, kind="ASSET", parent=""):
    from domain.models.account import Account

    return Account(code=code, name=name, kind=kind, parent_code=parent)


def test_parent_must_exist(in_memory_db):
    from domain.services.account_service import AccountValidationError

    service = _accounts(in_memory_db)
    with pytest.raises(AccountValidationError):
        service.create(_acc("A", "Con A", parent="KHONGCO"))


def test_account_cannot_be_its_own_parent(in_memory_db):
    from domain.services.account_service import AccountValidationError

    service = _accounts(in_memory_db)
    with pytest.raises(AccountValidationError):
        service.create(_acc("A", "Con A", parent="A"))


def test_cycle_is_rejected_on_update(in_memory_db):
    from domain.services.account_service import AccountValidationError

    service = _accounts(in_memory_db)
    service.create(_acc("D", "Tổng hợp"))
    service.create(_acc("A", "Con A", parent="D"))
    # Giờ ép D làm con của A → tạo vòng A→D→A.
    d = next(x for x in service.list_all() if x.code == "D")
    d.parent_code = "A"
    with pytest.raises(AccountValidationError):
        service.update(d)


def test_valid_parent_is_saved_and_normalized(in_memory_db):
    service = _accounts(in_memory_db)
    service.create(_acc("D", "Tổng hợp"))
    service.create(_acc("A", "Con A", parent="D"))
    assert service.parent_map() == {"A": "D"}


# --- cộng gộp trong báo cáo -----------------------------------------------


def _seed_rollup(conn):
    """D = A + B + C, thêm bút toán riêng cho D (mô hình 'cộng thêm')."""
    from datetime import date as _d

    from domain.models.journal import EntryStatus, JournalEntry, JournalLine
    from data.repositories.journal_repo import JournalRepository
    from domain.services.journal_service import JournalService

    service = _accounts(conn)
    service.create(_acc("D", "Tiền tổng hợp"))
    service.create(_acc("A", "Quỹ A", parent="D"))
    service.create(_acc("B", "Quỹ B", parent="D"))
    service.create(_acc("C", "Quỹ C", parent="D"))
    service.create(_acc("411", "Vốn", kind="EQUITY"))

    journal = JournalService(JournalRepository(conn))
    _MM = Decimal("1000000")

    def entry(ref, debit_code, amount):
        return JournalEntry(
            ref=ref, entry_date=_d(2026, 2, 10), description=ref,
            status=EntryStatus.POSTED,
            lines=[
                JournalLine(account_code=debit_code, debit=amount, credit=Decimal(0)),
                JournalLine(account_code="411", debit=Decimal(0), credit=amount),
            ],
        )

    journal.create(entry("EA", "A", 10 * _MM))
    journal.create(entry("EB", "B", 20 * _MM))
    journal.create(entry("EC", "C", 30 * _MM))
    journal.create(entry("ED", "D", 5 * _MM))   # bút toán riêng của tài khoản cha
    return conn


def _report(conn):
    from data.repositories.account_repo import AccountRepository
    from data.repositories.journal_repo import JournalRepository
    from domain.services.report_service import ReportService

    return ReportService(JournalRepository(conn), AccountRepository(conn))


_M = Decimal("1000000")
_PERIOD_START = date(2026, 1, 1)
_PERIOD_END = date(2026, 12, 31)


def test_aggregated_balances_rolls_children_into_parent(in_memory_db):
    conn = _seed_rollup(in_memory_db)
    balances = _report(conn).aggregated_balances()
    assert balances["A"] == 10 * _M
    assert balances["D"] == 65 * _M     # 5 riêng + 10 + 20 + 30


def test_trial_balance_parent_aggregates_without_double_counting(in_memory_db):
    from domain.models.report import ReportPeriod

    conn = _seed_rollup(in_memory_db)
    tb = _report(conn).trial_balance(ReportPeriod(_PERIOD_START, _PERIOD_END))

    d_row = next(r for r in tb.rows if r.code == "D")
    assert d_row.closing_debit == 65 * _M
    assert d_row.is_aggregate is True
    assert d_row.parent_code == ""

    a_row = next(r for r in tb.rows if r.code == "A")
    assert a_row.closing_debit == 10 * _M
    assert a_row.parent_code == "D"
    assert a_row.level == 1

    # Tổng cột chỉ tính dòng gốc: D (65) đối ứng 411 (65) — không cộng cả con.
    assert tb.total_closing_debit == 65 * _M
    assert tb.is_balanced


def test_balance_sheet_shows_only_parent(in_memory_db):
    conn = _seed_rollup(in_memory_db)
    bs = _report(conn).balance_sheet(_PERIOD_END)
    asset_codes = {l.code for l in bs.asset_lines}
    assert asset_codes == {"D"}                         # con đã gộp, ẩn khỏi CĐKT
    d_line = next(l for l in bs.asset_lines if l.code == "D")
    assert d_line.amount == 65 * _M
    assert bs.total_assets == 65 * _M
