"""Tests cho InvoiceImportService — phân loại bán/mua, chống trùng, đối tác lạ."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

_COMPANY_TAX = "0312654987"


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


def _importer(conn):
    from data.repositories.account_repo import AccountRepository
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.invoice_repo import InvoiceRepository
    from data.repositories.item_repo import ItemRepository
    from data.repositories.journal_repo import JournalRepository
    from data.repositories.partner_repo import PartnerRepository
    from data.repositories.settings_repo import SettingsRepository
    from domain.models.company import CompanyProfile
    from domain.services.company_service import CompanyService
    from domain.services.email_config_service import EmailConfigService
    from domain.services.inventory_service import InventoryService
    from domain.services.invoice_import_service import InvoiceImportService
    from domain.services.journal_service import JournalService
    from domain.services.purchase_service import PurchaseService
    from domain.services.sales_service import SalesService

    settings = SettingsRepository(conn)
    company = CompanyService(settings)
    company.save(CompanyProfile(name="CONG TY MINH", tax_code=_COMPANY_TAX))

    inventory = InventoryService(InventoryRepository(conn), ItemRepository(conn))
    journal = JournalService(JournalRepository(conn))
    partners = PartnerRepository(conn)
    accounts = AccountRepository(conn)
    invoices = InvoiceRepository(conn)
    sales = SalesService(invoices, inventory, journal, partners, accounts)
    purchase = PurchaseService(invoices, inventory, journal, partners, accounts)
    return InvoiceImportService(
        sales=sales, purchase=purchase, company=company,
        partner_repo=partners, invoice_repo=invoices,
        item_repo=ItemRepository(conn),
        email_config=EmailConfigService(settings),
    ), invoices, partners


def _parsed(*, seller_tax, buyer_tax, serial="1C22TAA", no="55"):
    from domain.services.einvoice_parser import ParsedInvoice, ParsedLine
    from domain.services.invoice_import_service import ParsedEmailInvoice

    parsed = ParsedInvoice(
        invoice_no=no, serial=serial, invoice_date=date(2026, 6, 18),
        seller_name="CONG TY BAN", seller_tax_code=seller_tax, seller_address="HCM",
        buyer_name="CONG TY MUA", buyer_tax_code=buyer_tax, buyer_address="HN",
        lines=[ParsedLine(
            name="Thep tam", unit="kg", quantity=Decimal("10"),
            unit_price=Decimal("1000"), vat_rate=Decimal("10"),
            amount=Decimal("10000"))],
    )
    return ParsedEmailInvoice(parsed=parsed, uid=10)


def test_classify_purchase_when_company_is_buyer(in_memory_db):
    from domain.models.invoice import InvoiceKind

    importer, invoices, _ = _importer(in_memory_db)
    # MST người mua == MST công ty → hóa đơn đầu vào (mua hàng).
    result = importer.persist([_parsed(seller_tax="0301234567", buyer_tax=_COMPANY_TAX)])
    assert result.imported == 1
    saved = invoices.list_all(InvoiceKind.PURCHASE)
    assert len(saved) == 1
    assert saved[0].partner_tax_code == "0301234567"   # đối tác = người bán


def test_classify_sale_when_company_is_seller(in_memory_db):
    from domain.models.invoice import InvoiceKind

    importer, invoices, _ = _importer(in_memory_db)
    result = importer.persist([_parsed(seller_tax=_COMPANY_TAX, buyer_tax="0309998887")])
    assert result.imported == 1
    saved = invoices.list_all(InvoiceKind.SALE)
    assert len(saved) == 1
    assert saved[0].partner_tax_code == "0309998887"   # đối tác = người mua


def test_unknown_partner_flagged_and_savable(in_memory_db):
    importer, invoices, partners = _importer(in_memory_db)
    item = _parsed(seller_tax="0301234567", buyer_tax=_COMPANY_TAX)
    result = importer.persist([item])
    assert result.unknown_partner == 1

    saved = invoices.find_by_ref("1C22TAA-55")
    assert importer._purchase.partner_is_unknown(saved) is True

    # Sau khi lưu đối tác vào danh mục → không còn báo đỏ.
    importer._purchase.update(saved, save_new_partner=True)
    assert partners.find_by_tax_code("0301234567") is not None
    assert importer._purchase.partner_is_unknown(saved) is False


def test_duplicate_invoice_is_skipped(in_memory_db):
    importer, _, _ = _importer(in_memory_db)
    item = _parsed(seller_tax="0301234567", buyer_tax=_COMPANY_TAX)
    first = importer.persist([item])
    assert first.imported == 1
    # Cùng số/ký hiệu → ref trùng → lần sau bỏ qua, không nhân đôi.
    second = importer.persist([_parsed(seller_tax="0301234567", buyer_tax=_COMPANY_TAX)])
    assert second.imported == 0
    assert second.skipped == 1


def test_known_partner_uses_existing_code(in_memory_db):
    from domain.models.partner import Partner, PartnerType

    importer, invoices, partners = _importer(in_memory_db)
    partners.insert(Partner(
        code="NCC01", name="CONG TY BAN", type=PartnerType.SUPPLIER,
        tax_code="0301234567"))
    importer.persist([_parsed(seller_tax="0301234567", buyer_tax=_COMPANY_TAX)])
    saved = invoices.find_by_ref("1C22TAA-55")
    assert saved.partner_code == "NCC01"               # khớp theo MST → dùng mã sẵn có
    assert importer._purchase.partner_is_unknown(saved) is False
