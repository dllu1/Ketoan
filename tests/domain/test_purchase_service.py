"""PurchaseService tests — inventory IN + input-VAT / payable postings."""
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
    from domain.services.purchase_service import PurchaseService

    inventory = InventoryService(InventoryRepository(conn), ItemRepository(conn))
    journal = JournalService(JournalRepository(conn))
    return PurchaseService(
        InvoiceRepository(conn), inventory, journal,
        PartnerRepository(conn), AccountRepository(conn),
    ), inventory, journal


def _seed_item(conn, code="HH001"):
    from data.repositories.item_repo import ItemRepository
    from domain.models.item import Item, ItemCategory

    ItemRepository(conn).insert(
        Item(code=code, name="Ống thép", category=ItemCategory.GOOD, unit="m")
    )


def _invoice(ref="HDM001"):
    from domain.models.invoice import Invoice, InvoiceLine, PaymentMethod

    return Invoice(
        ref=ref,
        invoice_date=date(2026, 6, 9),
        payment_method=PaymentMethod.CREDIT,
        partner_code="NCC01",
        partner_name="Cty Thép XYZ",
        description="Mua ống thép",
        lines=[
            InvoiceLine(
                item_code="HH001", item_name="Ống thép", unit="m",
                quantity=Decimal("10"), unit_price=Decimal("15000"),
                vat_rate=Decimal("10"), account_code="156",
            )
        ],
    )


def test_post_generates_inventory_in_and_balanced_journal(in_memory_db):
    _seed_item(in_memory_db)
    purchases, inventory, journal = _service(in_memory_db)
    purchases.create(_invoice(), save_new_partner=True)

    assert inventory.on_hand("HH001") == Decimal("10")
    assert inventory.average_cost("HH001") == Decimal("15000")

    entry = journal.find_by_ref("HDM001")
    assert entry is not None and entry.is_balanced
    dr_156 = next(l for l in entry.lines if l.account_code == "156")
    assert dr_156.debit == Decimal("150000")
    dr_vat = next(l for l in entry.lines if l.account_code == "1331")
    assert dr_vat.debit == Decimal("15000")
    cr_331 = next(l for l in entry.lines if l.account_code == "331")
    assert cr_331.credit == Decimal("165000")
    # Dòng phải trả (331) mang mã NCC để lên báo cáo công nợ; kho/thuế thì không.
    assert cr_331.partner_code == "NCC01"
    assert dr_156.partner_code == "" and dr_vat.partner_code == ""


def test_uncatalogued_item_keeps_name_from_invoice_line(in_memory_db):
    """Mua NVL chưa khai báo trong Danh mục: kho vẫn hiển thị tên ghi trên chứng từ."""
    from domain.models.invoice import Invoice, InvoiceLine, PaymentMethod

    purchases, inventory, _ = _service(in_memory_db)
    invoice = Invoice(
        ref="HDM-NVL",
        invoice_date=date(2026, 6, 9),
        payment_method=PaymentMethod.CREDIT,
        partner_code="NCC02",
        partner_name="Cty Vật tư",
        description="Mua sắt phi 20",
        lines=[
            InvoiceLine(
                item_code="S20", item_name="Sắt phi 20", unit="kg",
                quantity=Decimal("100"), unit_price=Decimal("12000"),
                vat_rate=Decimal("10"), account_code="152",
            )
        ],
    )
    purchases.create(invoice, save_new_partner=True)

    row = next(r for r in inventory.compute_nxt() if r.item_code == "S20")
    assert row.item_name == "Sắt phi 20"   # tên đến từ dòng hóa đơn, không phải Danh mục
    assert row.in_qty == Decimal("100")


def test_catalogued_name_still_wins_over_line(in_memory_db):
    """Khi mặt hàng đã có trong Danh mục, tên kho vẫn lấy theo Danh mục (giữ logic cũ)."""
    from domain.models.invoice import Invoice, InvoiceLine, PaymentMethod

    _seed_item(in_memory_db, code="HH001")  # tên Danh mục = "Ống thép"
    purchases, inventory, _ = _service(in_memory_db)
    invoice = Invoice(
        ref="HDM-CAT",
        invoice_date=date(2026, 6, 9),
        payment_method=PaymentMethod.CREDIT,
        partner_code="NCC03",
        partner_name="Cty Thép",
        lines=[
            InvoiceLine(
                item_code="HH001", item_name="Tên khác trên hóa đơn", unit="m",
                quantity=Decimal("5"), unit_price=Decimal("15000"),
                vat_rate=Decimal("10"), account_code="156",
            )
        ],
    )
    purchases.create(invoice, save_new_partner=True)

    row = next(r for r in inventory.compute_nxt() if r.item_code == "HH001")
    assert row.item_name == "Ống thép"


def test_kind_isolated_from_sales(in_memory_db):
    from domain.models.invoice import InvoiceKind

    _seed_item(in_memory_db)
    purchases, _, _ = _service(in_memory_db)
    purchases.create(_invoice(), save_new_partner=True)
    listed = purchases.list_all()
    assert listed and all(inv.kind is InvoiceKind.PURCHASE for inv in listed)


def test_new_supplier_saved_as_supplier_type(in_memory_db):
    from data.repositories.partner_repo import PartnerRepository
    from domain.models.partner import PartnerType

    _seed_item(in_memory_db)
    purchases, _, _ = _service(in_memory_db)
    purchases.create(_invoice(), save_new_partner=True)
    supplier = PartnerRepository(in_memory_db).find_by_code("NCC01")
    assert supplier is not None and supplier.type is PartnerType.SUPPLIER


def test_delete_reverses_inventory_and_journal(in_memory_db):
    _seed_item(in_memory_db)
    purchases, inventory, journal = _service(in_memory_db)
    saved = purchases.create(_invoice(), save_new_partner=True)
    assert inventory.on_hand("HH001") == Decimal("10")
    purchases.delete(saved)
    assert inventory.on_hand("HH001") == Decimal("0")
    assert journal.find_by_ref("HDM001") is None


def test_warehouse_account_and_definition_override(in_memory_db):
    """Mã kho (TK kho) trên dòng định tuyến cả NXT lẫn bút toán; TK Có chọn tay."""
    _seed_item(in_memory_db)  # HH001 = hàng hóa → mặc định kho 156
    purchases, inventory, journal = _service(in_memory_db)

    inv = _invoice(ref="HDM-KHO")
    inv.lines[0].account_code = "152"  # đẩy vào kho 152 thay vì 156
    inv.debit_account = "152"
    inv.credit_account = "111"         # trả bằng tiền mặt thay cho 331
    purchases.create(inv, save_new_partner=True)

    # NXT cập nhật đúng kho đã chọn.
    row = next(r for r in inventory.compute_nxt() if r.item_code == "HH001")
    assert row.account_code == "152"
    assert row.in_qty == Decimal("10")

    entry = journal.find_by_ref("HDM-KHO")
    assert entry is not None and entry.is_balanced
    assert next(l for l in entry.lines if l.account_code == "152").debit == Decimal("150000")
    assert next(l for l in entry.lines if l.account_code == "111").credit == Decimal("165000")
    assert not any(l.account_code == "331" for l in entry.lines)
