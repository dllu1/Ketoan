"""Hóa đơn mua hàng có dòng chi phí dịch vụ mua ngoài (không vào kho).

Chi phí (giao hàng, tiền điện, tiền nước…) chỉ có thành tiền: nó phải ghi Nợ TK
chi phí / Có phải trả như dòng hàng, nhưng *không* được sinh phát sinh kho, và
phải nhớ được nơi sẽ phân bổ tới để kết chuyển giá thành sau này.
"""
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


def _seed_item(conn, code="NVL01"):
    from data.repositories.item_repo import ItemRepository
    from domain.models.item import Item, ItemCategory

    ItemRepository(conn).insert(
        Item(code=code, name="Hạt nhựa", category=ItemCategory.MATERIAL, unit="kg")
    )


def _cost_line(name="Cước giao hàng", amount="2000000", target="155", debit="154"):
    from domain.models.invoice import InvoiceLine, InvoiceLineType

    # Chi phí lưu quantity=1 / unit_price=thành tiền để dùng chung công thức tiền.
    return InvoiceLine(
        item_code="",
        item_name=name,
        quantity=Decimal("1"),
        unit_price=Decimal(amount),
        vat_rate=Decimal("10"),
        line_type=InvoiceLineType.COST,
        debit_account=debit,
        allocation_target=target,
    )


def _invoice(ref="HD-COST-01", *, with_item=True, cost_lines=()):
    from domain.models.invoice import Invoice, InvoiceLine, PaymentMethod

    lines = []
    if with_item:
        lines.append(
            InvoiceLine(
                item_code="NVL01", item_name="Hạt nhựa", unit="kg",
                quantity=Decimal("100"), unit_price=Decimal("50000"),
                vat_rate=Decimal("10"), account_code="152", debit_account="152",
            )
        )
    lines.extend(cost_lines)
    return Invoice(
        ref=ref,
        invoice_date=date(2026, 3, 15),
        payment_method=PaymentMethod.CREDIT,
        partner_code="NCC09",
        partner_name="Cty Vận tải ABC",
        description="Mua NVL kèm cước giao hàng",
        lines=lines,
    )


def test_cost_line_posts_expense_but_no_inventory_movement(in_memory_db):
    _seed_item(in_memory_db)
    purchases, inventory, journal = _service(in_memory_db)

    purchases.create(
        _invoice(cost_lines=[_cost_line()]), save_new_partner=True
    )

    # Kho chỉ nhận 100kg NVL — cước giao hàng không tạo phát sinh kho nào.
    movements = inventory._repo.list_all()
    assert [(m.item_code, m.quantity) for m in movements] == [
        ("NVL01", Decimal("100"))
    ]

    entry = journal.list_all()[0]
    by_account = {ln.account_code: (ln.debit, ln.credit) for ln in entry.lines}
    # Nợ 152 tiền hàng, Nợ 154 chi phí dịch vụ, Nợ 1331 thuế, Có 331 tổng phải trả.
    assert by_account["152"][0] == Decimal("5000000")
    assert by_account["154"][0] == Decimal("2000000")
    assert by_account["1331"][0] == Decimal("700000")
    assert by_account["331"][1] == Decimal("7700000")
    assert sum(ln.debit for ln in entry.lines) == sum(ln.credit for ln in entry.lines)


def test_cost_only_invoice_is_valid_without_any_item_line(in_memory_db):
    """Hóa đơn tiền điện / tiền nước thuần chi phí vẫn ghi sổ được."""
    purchases, inventory, journal = _service(in_memory_db)

    purchases.create(
        _invoice(
            ref="HD-DIEN-03",
            with_item=False,
            cost_lines=[_cost_line("Tiền điện tháng 3", "1500000", "154", "627")],
        ),
        save_new_partner=True,
    )

    assert inventory._repo.list_all() == []
    entry = journal.list_all()[0]
    by_account = {ln.account_code: (ln.debit, ln.credit) for ln in entry.lines}
    assert by_account["627"][0] == Decimal("1500000")
    assert by_account["331"][1] == Decimal("1650000")


def test_cost_line_survives_a_save_reload_round_trip(in_memory_db):
    _seed_item(in_memory_db)
    purchases, _inventory, _journal = _service(in_memory_db)
    purchases.create(_invoice(cost_lines=[_cost_line()]), save_new_partner=True)

    reloaded = purchases.list_all()[0]
    assert [ln.item_code for ln in reloaded.item_lines] == ["NVL01"]
    cost = reloaded.cost_lines[0]
    assert cost.is_cost
    assert cost.item_name == "Cước giao hàng"
    assert cost.amount == Decimal("2000000")
    assert cost.allocation_target == "155"


def test_cost_allocations_group_by_target_account(in_memory_db):
    _seed_item(in_memory_db)
    purchases, _inventory, _journal = _service(in_memory_db)
    purchases.create(
        _invoice(cost_lines=[
            _cost_line("Cước giao hàng", "2000000", "155"),
            _cost_line("Tiền nước", "500000", "155"),
            _cost_line("Cước giao khách", "300000", "641"),
        ]),
        save_new_partner=True,
    )

    assert purchases.cost_allocations() == {
        "155": Decimal("2500000"),
        "641": Decimal("300000"),
    }


def test_cost_line_without_description_is_rejected(in_memory_db):
    from domain.services.purchase_service import PurchaseValidationError

    _seed_item(in_memory_db)
    purchases, _inventory, _journal = _service(in_memory_db)
    blank = _cost_line(name="", amount="900000")

    with pytest.raises(PurchaseValidationError, match="nội dung"):
        purchases.create(_invoice(cost_lines=[blank]), save_new_partner=True)
