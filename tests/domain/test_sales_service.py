"""SalesService tests — system_routing.png workflow + posting side-effects."""
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


def _service(conn):
    from data.repositories.account_repo import AccountRepository
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.invoice_repo import InvoiceRepository
    from data.repositories.item_repo import ItemRepository
    from data.repositories.journal_repo import JournalRepository
    from data.repositories.partner_repo import PartnerRepository
    from domain.services.inventory_service import InventoryService
    from domain.services.journal_service import JournalService
    from domain.services.sales_service import SalesService

    inventory = InventoryService(InventoryRepository(conn), ItemRepository(conn))
    journal = JournalService(JournalRepository(conn))
    return SalesService(
        InvoiceRepository(conn), inventory, journal,
        PartnerRepository(conn), AccountRepository(conn),
    ), inventory, journal


def _seed_stock(conn, code="HH001"):
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from domain.models.item import Item, ItemCategory
    from domain.services.inventory_service import InventoryService

    ItemRepository(conn).insert(
        Item(code=code, name="Ống thép", category=ItemCategory.GOOD, unit="m")
    )
    InventoryService(InventoryRepository(conn), ItemRepository(conn)).record_in(
        code, Decimal("100"), Decimal("10000")
    )


def _invoice(ref="HD001", partner_code="", quantity="10", price="15000"):
    from domain.models.invoice import Invoice, InvoiceLine, PaymentMethod

    return Invoice(
        ref=ref,
        invoice_date=date(2026, 6, 9),
        payment_method=PaymentMethod.CREDIT,
        partner_code=partner_code,
        partner_name="Cty TNHH ABC" if partner_code else "",
        description="Bán ống thép",
        lines=[
            InvoiceLine(
                item_code="HH001", item_name="Ống thép", unit="m",
                quantity=Decimal(quantity), unit_price=Decimal(price),
                vat_rate=Decimal("10"), account_code="156",
            )
        ],
    )


def test_post_generates_inventory_out_and_balanced_journal(in_memory_db):
    _seed_stock(in_memory_db)
    sales, inventory, journal = _service(in_memory_db)
    sales.create(_invoice())

    assert inventory.on_hand("HH001") == Decimal("90")  # 100 - 10

    entry = journal.find_by_ref("HD001")
    assert entry is not None
    assert entry.is_balanced
    # Dr 131 = 165000 (150000 + 10% VAT); Cr 511 150000 + Cr 3331 15000.
    debit_131 = next(l for l in entry.lines if l.account_code == "131")
    assert debit_131.debit == Decimal("165000")
    cogs = next(l for l in entry.lines if l.account_code == "632")
    assert cogs.debit == Decimal("100000")  # 10 * 10000 avg cost


def test_receivable_line_carries_partner_code(in_memory_db):
    # Dòng phải thu (131) phải mang mã khách hàng để lên báo cáo công nợ.
    _seed_stock(in_memory_db)
    sales, _, journal = _service(in_memory_db)
    sales.create(_invoice(ref="HD777", partner_code="KH001"))

    entry = journal.find_by_ref("HD777")
    line_131 = next(l for l in entry.lines if l.account_code == "131")
    assert line_131.partner_code == "KH001"
    # Doanh thu / thuế không gắn đối tượng.
    assert all(l.partner_code == "" for l in entry.lines
               if l.account_code in {"511", "3331", "632", "156"})


def test_guest_invoice_leaves_receivable_untagged(in_memory_db):
    _seed_stock(in_memory_db)
    sales, _, journal = _service(in_memory_db)
    sales.create(_invoice(ref="HD778", partner_code=""))  # khách lẻ

    entry = journal.find_by_ref("HD778")
    line_131 = next(l for l in entry.lines if l.account_code == "131")
    assert line_131.partner_code == ""


def test_new_partner_saved_to_directory_when_requested(in_memory_db):
    from data.repositories.partner_repo import PartnerRepository

    _seed_stock(in_memory_db)
    sales, _, _ = _service(in_memory_db)
    assert sales.partner_exists("KH999") is False
    sales.create(_invoice(partner_code="KH999"), save_new_partner=True)
    assert PartnerRepository(in_memory_db).find_by_code("KH999") is not None


def test_new_partner_not_saved_keeps_one_time_document(in_memory_db):
    from data.repositories.partner_repo import PartnerRepository

    _seed_stock(in_memory_db)
    sales, _, _ = _service(in_memory_db)
    sales.create(_invoice(partner_code="KH888"), save_new_partner=False)
    # Document persisted, but no directory record created.
    assert sales.search("KH888")
    assert PartnerRepository(in_memory_db).find_by_code("KH888") is None


def test_existing_partner_metadata_refreshed(in_memory_db):
    from data.repositories.partner_repo import PartnerRepository
    from domain.models.partner import Partner

    _seed_stock(in_memory_db)
    PartnerRepository(in_memory_db).insert(Partner(code="KH001", name="Tên cũ"))
    sales, _, _ = _service(in_memory_db)

    inv = _invoice(partner_code="KH001")
    inv.partner_name = "Tên mới"
    sales.create(inv)

    refreshed = PartnerRepository(in_memory_db).find_by_code("KH001")
    assert refreshed.name == "Tên mới"


def test_delete_reverses_inventory_and_journal(in_memory_db):
    _seed_stock(in_memory_db)
    sales, inventory, journal = _service(in_memory_db)
    saved = sales.create(_invoice())
    assert inventory.on_hand("HH001") == Decimal("90")

    sales.delete(saved)
    assert inventory.on_hand("HH001") == Decimal("100")
    assert journal.find_by_ref("HD001") is None


def test_draft_has_no_side_effects(in_memory_db):
    from domain.models.invoice import InvoiceStatus

    _seed_stock(in_memory_db)
    sales, inventory, journal = _service(in_memory_db)
    inv = _invoice()
    inv.status = InvoiceStatus.DRAFT
    sales.create(inv)
    assert inventory.on_hand("HH001") == Decimal("100")
    assert journal.find_by_ref("HD001") is None


def test_unpost_clears_prior_side_effects(in_memory_db):
    """Ghi sổ rồi sửa lại lưu nháp phải gỡ hết phát sinh kho + bút toán cũ."""
    from domain.models.invoice import InvoiceStatus

    _seed_stock(in_memory_db)
    sales, inventory, journal = _service(in_memory_db)
    saved = sales.create(_invoice())
    assert inventory.on_hand("HH001") == Decimal("90")
    assert journal.find_by_ref("HD001") is not None

    saved.status = InvoiceStatus.DRAFT
    sales.update(saved)
    assert inventory.on_hand("HH001") == Decimal("100")   # xuất kho đã hoàn
    assert journal.find_by_ref("HD001") is None            # bút toán đã gỡ


def test_duplicate_ref_rejected(in_memory_db):
    from domain.services.sales_service import SalesValidationError

    _seed_stock(in_memory_db)
    sales, _, _ = _service(in_memory_db)
    sales.create(_invoice(ref="HD777"))
    with pytest.raises(SalesValidationError):
        sales.create(_invoice(ref="HD777"))


def test_definition_accounts_override_sales_posting(in_memory_db):
    """TK Nợ/Có chọn tay + mã kho trên dòng định tuyến lại bút toán bán hàng."""
    _seed_stock(in_memory_db)  # HH001: 100 @ 10.000, nhập kho mặc định 156
    sales, inventory, journal = _service(in_memory_db)

    inv = _invoice(ref="HD-DK")
    inv.lines[0].account_code = "152"  # giá vốn ghi Có kho 152
    inv.debit_account = "111"          # thu tiền mặt thay vì 131
    inv.credit_account = "5111"        # doanh thu chi tiết thay vì 511
    sales.create(inv)

    assert inventory.on_hand("HH001") == Decimal("90")

    entry = journal.find_by_ref("HD-DK")
    assert entry is not None and entry.is_balanced
    assert next(l for l in entry.lines if l.account_code == "111").debit == Decimal("165000")
    assert next(l for l in entry.lines if l.account_code == "5111").credit == Decimal("150000")
    assert next(l for l in entry.lines if l.account_code == "152").credit == Decimal("100000")
    assert not any(l.account_code in ("131", "511") for l in entry.lines)
