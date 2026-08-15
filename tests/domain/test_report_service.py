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


def test_income_statement_survives_year_end_closing(seeded):
    """Kết chuyển 911 không được làm rỗng KQKD (và kéo theo tờ khai TNDN).

    Sau KC-DT/KC-CP thì 511 vừa có Có vừa có Nợ nên số phát sinh thuần = 0 —
    báo cáo phải bỏ qua chính các bút toán kết chuyển, không phải trả về trắng.
    """
    journal = _journal(seeded)
    journal.create(_entry("KC-DT/Q1", date(2026, 3, 31),
                          [("511", 100 * _M, _Z), ("911", _Z, 100 * _M)]))
    journal.create(_entry("KC-CP/Q1", date(2026, 3, 31),
                          [("911", 65 * _M, _Z),
                           ("632", _Z, 60 * _M), ("642", _Z, 5 * _M)]))
    journal.create(_entry("KC-LN/Q1", date(2026, 3, 31),
                          [("911", 35 * _M, _Z), ("4212", _Z, 35 * _M)]))

    pl = _report(seeded).income_statement(_PERIOD)
    assert pl.total_revenue == 100 * _M
    assert pl.total_expense == 65 * _M
    assert pl.profit_before_tax == 35 * _M


def test_income_statement_keeps_cogs_transfer_kc_gv(in_memory_db):
    """KC-GV (Nợ 632 / Có 155) là chi phí thật — không nằm trong nhóm bị loại."""
    journal = _journal(in_memory_db)
    journal.create(_entry("BH01", date(2026, 1, 15),
                          [("131", 100 * _M, _Z), ("511", _Z, 100 * _M)]))
    journal.create(_entry("KC-GV/Q1", date(2026, 3, 31),
                          [("632", 60 * _M, _Z), ("155", _Z, 60 * _M)]))

    pl = _report(in_memory_db).income_statement(_PERIOD)
    assert pl.total_expense == 60 * _M
    assert pl.profit_before_tax == 40 * _M


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


def test_income_statement_b02_maps_indicators(seeded):
    """Mẫu B02-DNN: doanh thu [01], giá vốn [11], chi phí QLKD [24] và các dòng cộng."""
    kq = _report(seeded).income_statement_b02(_PERIOD)
    assert kq.amount("01") == 100 * _M          # Có 511
    assert kq.amount("02") == _Z
    assert kq.amount("10") == 100 * _M          # doanh thu thuần
    assert kq.amount("11") == 60 * _M           # Nợ 632
    assert kq.amount("20") == 40 * _M           # lợi nhuận gộp
    assert kq.amount("24") == 5 * _M            # Nợ 642
    assert kq.amount("30") == 35 * _M
    assert kq.amount("50") == 35 * _M
    assert kq.amount("60") == 35 * _M           # chưa hạch toán 821


def test_income_statement_b02_full_form(in_memory_db):
    journal = _journal(in_memory_db)
    journal.create(_entry("BH", date(2026, 1, 10),
                          [("131", 200 * _M, _Z), ("511", _Z, 200 * _M)]))
    # Hàng bán bị trả lại — TT133 ghi thẳng vào bên Nợ 511 → [02].
    journal.create(_entry("TL", date(2026, 1, 20),
                          [("511", 20 * _M, _Z), ("131", _Z, 20 * _M)]))
    journal.create(_entry("GV", date(2026, 1, 31),
                          [("632", 120 * _M, _Z), ("156", _Z, 120 * _M)]))
    journal.create(_entry("DTTC", date(2026, 2, 5),
                          [("112", 3 * _M, _Z), ("515", _Z, 3 * _M)]))
    journal.create(_entry("LAIVAY", date(2026, 2, 10),
                          [("6351", 8 * _M, _Z), ("112", _Z, 8 * _M)]))
    journal.create(_entry("QLDN", date(2026, 2, 28),
                          [("642", 15 * _M, _Z), ("111", _Z, 15 * _M)]))
    journal.create(_entry("TNK", date(2026, 3, 1),
                          [("111", 2 * _M, _Z), ("711", _Z, 2 * _M)]))
    journal.create(_entry("CPK", date(2026, 3, 2),
                          [("811", 6 * _M, _Z), ("111", _Z, 6 * _M)]))
    journal.create(_entry("TNDN", date(2026, 3, 31),
                          [("821", 4 * _M, _Z), ("3334", _Z, 4 * _M)]))

    kq = _report(in_memory_db).income_statement_b02(_PERIOD)
    assert kq.amount("01") == 200 * _M
    assert kq.amount("02") == 20 * _M
    assert kq.amount("10") == 180 * _M
    assert kq.amount("11") == 120 * _M
    assert kq.amount("20") == 60 * _M
    assert kq.amount("21") == 3 * _M
    assert kq.amount("22") == 8 * _M            # 6351 nằm trong chi phí tài chính
    assert kq.amount("23") == 8 * _M            # "trong đó: chi phí lãi vay"
    assert kq.amount("24") == 15 * _M
    assert kq.amount("30") == 40 * _M           # 60 + 3 − 8 − 15
    assert kq.amount("31") == 2 * _M
    assert kq.amount("32") == 6 * _M
    assert kq.amount("40") == -4 * _M           # lỗ khác, in trong ngoặc đơn
    assert kq.amount("50") == 36 * _M
    assert kq.amount("51") == 4 * _M
    assert kq.amount("60") == 32 * _M


def test_income_statement_b02_survives_year_end_transfer(in_memory_db):
    """Sau Kết chuyển (F11) mẫu B02 vẫn có số — bút toán 911 bị loại như KQKD cũ."""
    journal = _journal(in_memory_db)
    journal.create(_entry("BH", date(2026, 1, 10),
                          [("131", 100 * _M, _Z), ("511", _Z, 100 * _M)]))
    journal.create(_entry("KC-DT/2026", date(2026, 3, 31),
                          [("511", 100 * _M, _Z), ("911", _Z, 100 * _M)]))

    service = _report(in_memory_db)
    kq = service.income_statement_b02(_PERIOD)
    assert kq.amount("01") == 100 * _M
    assert kq.amount("02") == _Z                # kết chuyển không phải giảm trừ
    assert kq.amount("50") == service.income_statement(_PERIOD).profit_before_tax


def test_income_statement_b02_prior_year_column(in_memory_db):
    journal = _journal(in_memory_db)
    journal.create(_entry("BH25", date(2025, 2, 10),
                          [("131", 70 * _M, _Z), ("511", _Z, 70 * _M)]))
    journal.create(_entry("BH26", date(2026, 2, 10),
                          [("131", 110 * _M, _Z), ("511", _Z, 110 * _M)]))

    kq = _report(in_memory_db).income_statement_b02(_PERIOD)
    assert kq.prior_period.start == date(2025, 1, 1)
    assert kq.amount("10") == 110 * _M
    assert kq.amount("10", prior=True) == 70 * _M


def test_cash_flow_statement_b03_maps_indicators(seeded):
    """Mẫu B03-DNN: thu bán hàng vào [01], chi quản lý vào [02], cộng lên [20]."""
    cf = _report(seeded).cash_flow_statement(_PERIOD)
    assert cf.amount("01") == 100 * _M          # Nợ 111 / Có 511
    assert cf.amount("02") == -5 * _M           # Nợ 642 / Có 111
    assert cf.amount("20") == 95 * _M
    assert cf.amount("60") == 200 * _M          # tồn quỹ đầu kỳ
    assert cf.amount("70") == 295 * _M          # khớp số dư cuối kỳ


def test_cash_flow_statement_b03_classifies_every_activity(in_memory_db):
    journal = _journal(in_memory_db)
    journal.create(_entry("VAY", date(2026, 1, 5),
                          [("112", 500 * _M, _Z), ("341", _Z, 500 * _M)]))
    journal.create(_entry("TSCD", date(2026, 1, 20),
                          [("211", 300 * _M, _Z), ("112", _Z, 300 * _M)]))
    journal.create(_entry("LUONG", date(2026, 2, 28),
                          [("334", 40 * _M, _Z), ("111", _Z, 40 * _M)]))
    journal.create(_entry("LAIVAY", date(2026, 3, 10),
                          [("635", 10 * _M, _Z), ("112", _Z, 10 * _M)]))
    journal.create(_entry("TNDN", date(2026, 3, 20),
                          [("3334", 20 * _M, _Z), ("112", _Z, 20 * _M)]))
    # Nộp tiền mặt vào ngân hàng: chỉ luân chuyển nội bộ, không lên báo cáo.
    journal.create(_entry("NOPNH", date(2026, 3, 25),
                          [("112", 30 * _M, _Z), ("111", _Z, 30 * _M)]))

    cf = _report(in_memory_db).cash_flow_statement(_PERIOD)
    assert cf.amount("33") == 500 * _M          # tiền thu từ đi vay
    assert cf.amount("21") == -300 * _M         # chi mua sắm TSCĐ
    assert cf.amount("03") == -40 * _M          # chi trả người lao động
    assert cf.amount("04") == -10 * _M          # lãi vay đã trả
    assert cf.amount("05") == -20 * _M          # thuế TNDN đã nộp
    assert cf.amount("20") == -70 * _M
    assert cf.amount("30") == -300 * _M
    assert cf.amount("40") == 500 * _M
    assert cf.amount("50") == 130 * _M          # = 500 − 300 − 40 − 10 − 20


def test_cash_flow_statement_b03_net_change_matches_cash_balance(seeded):
    """[50] luôn bằng chênh lệch tồn quỹ — kể cả khi có chuyển tiền nội bộ."""
    service = _report(seeded)
    cf = service.cash_flow_statement(_PERIOD)
    quy = service.cash_flow(_PERIOD)
    assert cf.amount("50") == quy.net_change
    assert cf.amount("70") == quy.closing_balance


def test_cash_flow_statement_b03_prior_year_column(in_memory_db):
    journal = _journal(in_memory_db)
    journal.create(_entry("BH25", date(2025, 2, 10),
                          [("111", 80 * _M, _Z), ("511", _Z, 80 * _M)]))
    journal.create(_entry("BH26", date(2026, 2, 10),
                          [("111", 90 * _M, _Z), ("511", _Z, 90 * _M)]))

    cf = _report(in_memory_db).cash_flow_statement(_PERIOD)
    assert cf.prior_period.start == date(2025, 1, 1)
    assert cf.prior_period.end == date(2025, 3, 31)
    assert cf.amount("01") == 90 * _M
    assert cf.amount("01", prior=True) == 80 * _M


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
