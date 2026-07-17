"""TaxService tests — VAT aggregation from invoices + CIT brackets, no Qt."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.models.invoice import (
    Invoice,
    InvoiceKind,
    InvoiceLine,
    InvoiceStatus,
)
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


def _tax(conn):
    from data.repositories.account_repo import AccountRepository
    from data.repositories.invoice_repo import InvoiceRepository
    from data.repositories.journal_repo import JournalRepository
    from domain.services.report_service import ReportService
    from domain.services.tax_service import TaxService

    reports = ReportService(JournalRepository(conn), AccountRepository(conn))
    return TaxService(InvoiceRepository(conn), reports)


_Z = Decimal("0")
_M = Decimal("1000000")
_PERIOD = ReportPeriod(start=date(2026, 1, 1), end=date(2026, 3, 31))


def _line(qty, price, rate):
    return InvoiceLine(item_code="X", quantity=Decimal(qty),
                       unit_price=Decimal(price), vat_rate=Decimal(rate))


def _invoice(ref, no, day, kind, lines, status=InvoiceStatus.POSTED):
    return Invoice(ref=ref, invoice_no=no, invoice_date=day, kind=kind,
                   status=status, partner_name="ĐT", partner_tax_code="0100000000",
                   lines=lines)


@pytest.fixture
def seeded(in_memory_db):
    from data.repositories.invoice_repo import InvoiceRepository
    from data.repositories.journal_repo import JournalRepository
    from domain.services.journal_service import JournalService

    inv = InvoiceRepository(in_memory_db)
    # Output: two rates on one invoice → 1,000,000 + 800,000 VAT.
    inv.insert(_invoice("BH01", "0000123", date(2026, 2, 10), InvoiceKind.SALE,
                        [_line("10", "1000000", "10"), _line("5", "2000000", "8")]))
    # Input invoice → 500,000 VAT.
    inv.insert(_invoice("MH01", "0000999", date(2026, 2, 12), InvoiceKind.PURCHASE,
                        [_line("100", "50000", "10")]))
    # A draft and an out-of-range invoice — both excluded.
    inv.insert(_invoice("BH-D", "DRAFT", date(2026, 2, 1), InvoiceKind.SALE,
                        [_line("1", "1000000", "10")], status=InvoiceStatus.DRAFT))
    inv.insert(_invoice("BH99", "0000888", date(2026, 5, 1), InvoiceKind.SALE,
                        [_line("1", "1000000", "10")]))

    journal = JournalService(JournalRepository(in_memory_db))
    journal.create(JournalEntry(
        ref="DT01", entry_date=date(2026, 1, 20), status=EntryStatus.POSTED,
        lines=[JournalLine("111", debit=100 * _M), JournalLine("511", credit=100 * _M)],
    ))
    journal.create(JournalEntry(
        ref="GV01", entry_date=date(2026, 2, 20), status=EntryStatus.POSTED,
        lines=[JournalLine("632", debit=60 * _M), JournalLine("156", credit=60 * _M)],
    ))
    return in_memory_db


def test_vat_report_payable(seeded):
    vat = _tax(seeded).vat_report(_PERIOD)
    assert vat.output_vat == Decimal("1800000")
    assert vat.input_vat == Decimal("500000")
    assert vat.vat_payable == Decimal("1300000")


def test_vat_excludes_draft_and_out_of_range(seeded):
    vat = _tax(seeded).vat_report(_PERIOD)
    assert {r.invoice_no for r in vat.output_rows} == {"0000123"}
    assert vat.output_taxable == 20 * _M


def test_vat_rate_groups(seeded):
    vat = _tax(seeded).vat_report(_PERIOD)
    rates = {g.rate: (g.taxable, g.vat) for g in vat.output_groups}
    assert rates[Decimal("8")] == (10 * _M, Decimal("800000"))
    assert rates[Decimal("10")] == (10 * _M, Decimal("1000000"))


def test_cit_report_low_revenue_15_percent(seeded):
    cit = _tax(seeded).cit_report(_PERIOD)
    assert cit.revenue == 100 * _M
    assert cit.profit_before_tax == 40 * _M
    assert cit.rate == Decimal("0.15")
    assert cit.tax_amount == 6 * _M
    assert cit.profit_after_tax == 34 * _M


@pytest.mark.parametrize("revenue,rate", [
    ("10000000000", "0.15"),   # < 15 tỷ
    ("15000000000", "0.17"),   # đúng ngưỡng 15 tỷ
    ("40000000000", "0.17"),
    ("50000000000", "0.20"),   # đúng ngưỡng 50 tỷ
    ("80000000000", "0.20"),
])
def test_cit_rate_brackets(revenue, rate):
    from domain.services.tax_service import TaxService

    assert TaxService.cit_rate(Decimal(revenue)) == Decimal(rate)


def test_cit_covers_full_year_regardless_of_range(in_memory_db):
    """Chọn kỳ Q1 nhưng TNDN vẫn gộp doanh thu cả năm để chọn đúng bậc thuế."""
    from data.repositories.journal_repo import JournalRepository
    from domain.services.journal_service import JournalService

    journal = JournalService(JournalRepository(in_memory_db))
    # 10 tỷ trong Q1 + 8 tỷ tháng 9 (ngoài khoảng chọn) = 18 tỷ cả năm → bậc 17%.
    journal.create(JournalEntry(
        ref="DT-Q1", entry_date=date(2026, 3, 10), status=EntryStatus.POSTED,
        lines=[JournalLine("111", debit=10_000 * _M), JournalLine("511", credit=10_000 * _M)],
    ))
    journal.create(JournalEntry(
        ref="DT-Q3", entry_date=date(2026, 9, 10), status=EntryStatus.POSTED,
        lines=[JournalLine("111", debit=8_000 * _M), JournalLine("511", credit=8_000 * _M)],
    ))
    cit = _tax(in_memory_db).cit_report(_PERIOD)   # _PERIOD chỉ là Q1
    assert cit.revenue == 18_000 * _M
    assert cit.rate == Decimal("0.17")
    # Kỳ báo cáo trả về đã mở rộng thành cả năm.
    assert (cit.period.start, cit.period.end) == (date(2026, 1, 1), date(2026, 12, 31))


def test_cit_loss_yields_zero_tax(in_memory_db):
    from data.repositories.journal_repo import JournalRepository
    from domain.services.journal_service import JournalService

    JournalService(JournalRepository(in_memory_db)).create(JournalEntry(
        ref="LOSS", entry_date=date(2026, 2, 1), status=EntryStatus.POSTED,
        lines=[JournalLine("642", debit=5 * _M), JournalLine("111", credit=5 * _M)],
    ))
    cit = _tax(in_memory_db).cit_report(_PERIOD)
    assert cit.profit_before_tax == -5 * _M
    assert cit.tax_amount == _Z
