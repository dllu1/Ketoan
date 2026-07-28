"""Định mức theo quy cách đóng gói (thùng carton = N thành phẩm → 1/N)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.models.bom import BomLine


def test_apply_packaging_derives_quantity_per():
    line = BomLine(product_code="TP", material_code="THUNG",
                   pieces_per_pack=Decimal("25"))
    line.apply_packaging()
    assert line.quantity_per == Decimal(1) / Decimal("25")


def test_apply_packaging_noop_without_pack():
    line = BomLine(product_code="TP", material_code="THEP",
                   quantity_per=Decimal("0.8"))
    line.apply_packaging()
    assert line.quantity_per == Decimal("0.8")   # NVL thường giữ nguyên


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


def _bom(conn):
    from data.repositories.bom_repo import BomRepository
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from domain.services.bom_service import BomService
    from domain.services.inventory_service import InventoryService

    inventory = InventoryService(InventoryRepository(conn), ItemRepository(conn))
    return BomService(BomRepository(conn), inventory, ItemRepository(conn))


def _seed_box(conn):
    from data.repositories.item_repo import ItemRepository
    from domain.models.item import Item, ItemCategory

    repo = ItemRepository(conn)
    repo.insert(Item(code="TP01", name="Cây thép", category=ItemCategory.PRODUCT,
                     unit="cây"))
    repo.insert(Item(code="THUNG", name="Thùng carton", category=ItemCategory.MATERIAL,
                     unit="thùng", unit_price=Decimal("50000")))


def test_packaging_round_trips_and_derives(in_memory_db):
    _seed_box(in_memory_db)
    service = _bom(in_memory_db)
    service.save("TP01", [
        BomLine(product_code="TP01", material_code="THUNG",
                pieces_per_pack=Decimal("25")),
    ])
    loaded = service.load("TP01").lines
    assert len(loaded) == 1
    assert loaded[0].pieces_per_pack == Decimal("25")
    assert loaded[0].quantity_per == Decimal(1) / Decimal("25")


def test_material_cost_matches_one_box_per_pack(in_memory_db):
    _seed_box(in_memory_db)
    service = _bom(in_memory_db)
    service.save("TP01", [
        BomLine(product_code="TP01", material_code="THUNG",
                pieces_per_pack=Decimal("25")),
    ])
    # Sản xuất đúng 25 cây → tiêu hao đúng 1 thùng → chi phí = 1 × 50.000.
    cost = service.material_cost("TP01", Decimal("25"))
    assert cost == Decimal("50000")
