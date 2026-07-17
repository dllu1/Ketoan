"""InventoryService tests — weighted-average costing + NXT report."""
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
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from domain.services.inventory_service import InventoryService

    return InventoryService(InventoryRepository(conn), ItemRepository(conn))


def _seed_item(conn, code="HH001", category="156"):
    from data.repositories.item_repo import ItemRepository
    from domain.models.item import Item, ItemCategory

    ItemRepository(conn).insert(
        Item(code=code, name="Ống thép D60", category=ItemCategory(category), unit="m")
    )


def test_weighted_average_cost(in_memory_db):
    _seed_item(in_memory_db)
    svc = _service(in_memory_db)
    svc.record_in("HH001", Decimal("100"), Decimal("10000"))
    svc.record_in("HH001", Decimal("100"), Decimal("20000"))
    # (100*10000 + 100*20000) / 200 = 15000
    assert svc.average_cost("HH001") == Decimal("15000")
    assert svc.on_hand("HH001") == Decimal("200")


def test_out_costed_at_running_average(in_memory_db):
    _seed_item(in_memory_db)
    svc = _service(in_memory_db)
    svc.record_in("HH001", Decimal("100"), Decimal("10000"))
    svc.record_in("HH001", Decimal("100"), Decimal("20000"))
    out = svc.record_out("HH001", Decimal("50"))
    assert out.unit_cost == Decimal("15000")
    assert svc.on_hand("HH001") == Decimal("150")
    # Average is unchanged by an OUT movement.
    assert svc.average_cost("HH001") == Decimal("15000")


def test_record_out_insufficient_stock_when_disallowed(in_memory_db):
    from domain.services.inventory_service import InventoryError

    _seed_item(in_memory_db)
    svc = _service(in_memory_db)
    svc.record_in("HH001", Decimal("10"), Decimal("1000"))
    with pytest.raises(InventoryError):
        svc.record_out("HH001", Decimal("20"), allow_negative=False)


def test_nxt_report_opening_in_out_closing(in_memory_db):
    from domain.models.inventory import MovementKind

    _seed_item(in_memory_db)
    svc = _service(in_memory_db)
    svc.record_in("HH001", Decimal("100"), Decimal("10000"),
                  move_date=date(2026, 1, 1), kind=MovementKind.OPENING)
    svc.record_in("HH001", Decimal("50"), Decimal("10000"),
                  move_date=date(2026, 6, 10))
    svc.record_out("HH001", Decimal("30"), move_date=date(2026, 6, 15))

    rows = svc.compute_nxt(date(2026, 6, 1), date(2026, 6, 30))
    row = rows[0]
    assert row.opening_qty == Decimal("100")
    assert row.in_qty == Decimal("50")
    assert row.out_qty == Decimal("30")
    assert row.closing_qty == Decimal("120")
    assert row.closing_value == Decimal("1200000")  # 120 * 10000


def test_nxt_row_reports_unit_price_per_phase(in_memory_db):
    from domain.models.inventory import MovementKind

    _seed_item(in_memory_db)
    svc = _service(in_memory_db)
    svc.record_in("HH001", Decimal("100"), Decimal("10000"),
                  move_date=date(2026, 1, 1), kind=MovementKind.OPENING)
    svc.record_in("HH001", Decimal("50"), Decimal("16000"),
                  move_date=date(2026, 6, 10))
    svc.record_out("HH001", Decimal("30"), move_date=date(2026, 6, 15))

    row = svc.compute_nxt(date(2026, 6, 1), date(2026, 6, 30))[0]
    assert row.opening_price == Decimal("10000")   # 1,000,000 / 100
    assert row.in_price == Decimal("16000")        # 800,000 / 50
    # Xuất costed at running weighted average = (1,000,000 + 800,000) / 150 = 12,000.
    assert row.out_price == Decimal("12000")
    assert row.closing_price == Decimal("12000")   # 1,440,000 / 120


def test_remove_source_drops_movements(in_memory_db):
    _seed_item(in_memory_db)
    svc = _service(in_memory_db)
    svc.record_in("HH001", Decimal("10"), Decimal("1000"), source_ref="HD001")
    svc.remove_source("HD001")
    assert svc.on_hand("HH001") == Decimal("0")
