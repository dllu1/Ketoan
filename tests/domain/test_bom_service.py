"""BomService tests — định mức persistence + material-cost computation."""
from __future__ import annotations

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
    from data.repositories.bom_repo import BomRepository
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from domain.services.bom_service import BomService
    from domain.services.inventory_service import InventoryService

    inventory = InventoryService(InventoryRepository(conn), ItemRepository(conn))
    return BomService(BomRepository(conn), inventory, ItemRepository(conn))


def _seed_item(conn, code, category, unit_price="0"):
    from data.repositories.item_repo import ItemRepository
    from domain.models.item import Item, ItemCategory

    ItemRepository(conn).insert(
        Item(code=code, name=f"Mặt hàng {code}", category=ItemCategory(category),
             unit="kg", unit_price=Decimal(unit_price))
    )


def _line(product, material, qty):
    from domain.models.bom import BomLine

    return BomLine(product_code=product, material_code=material,
                   quantity_per=Decimal(qty))


def test_save_load_roundtrip_enriches_name_unit(in_memory_db):
    svc = _service(in_memory_db)
    _seed_item(in_memory_db, "TP01", "155")
    _seed_item(in_memory_db, "NVL01", "152")
    svc.save("TP01", [_line("TP01", "NVL01", "2.5")])
    bom = svc.load("TP01")
    assert len(bom.lines) == 1
    assert bom.lines[0].quantity_per == Decimal("2.5")
    assert bom.lines[0].material_name == "Mặt hàng NVL01"
    assert bom.lines[0].unit == "kg"


def test_material_cost_uses_catalog_price_when_no_stock(in_memory_db):
    svc = _service(in_memory_db)
    _seed_item(in_memory_db, "TP01", "155")
    _seed_item(in_memory_db, "NVL01", "152", unit_price="10000")
    _seed_item(in_memory_db, "NVL02", "152", unit_price="5000")
    svc.save("TP01", [
        _line("TP01", "NVL01", "2"),
        _line("TP01", "NVL02", "3"),
    ])
    # produced 10 units: (2*10*10000) + (3*10*5000) = 200000 + 150000 = 350000
    assert svc.material_cost("TP01", Decimal("10")) == Decimal("350000")


def test_material_cost_prefers_inventory_average(in_memory_db):
    svc = _service(in_memory_db)
    _seed_item(in_memory_db, "TP01", "155")
    _seed_item(in_memory_db, "NVL01", "152", unit_price="10000")

    # Real stock at 12,000/kg should override the 10,000 catalog price.
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from domain.services.inventory_service import InventoryService

    inventory = InventoryService(
        InventoryRepository(in_memory_db), ItemRepository(in_memory_db)
    )
    inventory.record_in("NVL01", Decimal("100"), Decimal("12000"))

    svc.save("TP01", [_line("TP01", "NVL01", "2")])
    # produced 5 units: 2*5*12000 = 120000
    assert svc.material_cost("TP01", Decimal("5")) == Decimal("120000")


def test_save_drops_empty_lines(in_memory_db):
    svc = _service(in_memory_db)
    _seed_item(in_memory_db, "TP01", "155")
    _seed_item(in_memory_db, "NVL01", "152")
    svc.save("TP01", [
        _line("TP01", "NVL01", "1"),
        _line("TP01", "", "0"),  # empty
    ])
    assert len(svc.load("TP01").lines) == 1
