"""OpeningBalanceService tests — save/load, report baseline, NXT push."""
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
    from data.repositories.opening_repo import OpeningBalanceRepository
    from domain.services.inventory_service import InventoryService
    from domain.services.opening_service import OpeningBalanceService

    inventory = InventoryService(InventoryRepository(conn), ItemRepository(conn))
    return OpeningBalanceService(
        OpeningBalanceRepository(conn), inventory, ItemRepository(conn)
    )


def _seed_item(conn, code="NVL01", category="152"):
    from data.repositories.item_repo import ItemRepository
    from domain.models.item import Item, ItemCategory

    ItemRepository(conn).insert(
        Item(code=code, name="Thép tấm", category=ItemCategory(category), unit="kg")
    )


def _ob(year, account, item="", *, qty="0", value="0", debit="0", credit="0"):
    from domain.models.opening import OpeningBalance

    return OpeningBalance(
        fiscal_year=year, account_code=account, item_code=item,
        opening_qty=Decimal(qty), opening_value=Decimal(value),
        opening_debit=Decimal(debit), opening_credit=Decimal(credit),
    )


def test_save_load_roundtrip(in_memory_db):
    svc = _service(in_memory_db)
    _seed_item(in_memory_db)
    svc.save(2026, [_ob(2026, "152", "NVL01", qty="100", value="5000000")])
    rows = svc.load(2026)
    assert len(rows) == 1
    assert rows[0].item_code == "NVL01"
    assert rows[0].opening_qty == Decimal("100")
    assert rows[0].opening_value == Decimal("5000000")


def test_save_is_idempotent_replace(in_memory_db):
    svc = _service(in_memory_db)
    _seed_item(in_memory_db)
    svc.save(2026, [_ob(2026, "152", "NVL01", qty="100", value="5000000")])
    svc.save(2026, [_ob(2026, "152", "NVL01", qty="80", value="4000000")])
    rows = svc.load(2026)
    assert len(rows) == 1
    assert rows[0].opening_qty == Decimal("80")


def test_account_openings_sums_item_value_as_debit(in_memory_db):
    svc = _service(in_memory_db)
    _seed_item(in_memory_db)
    _seed_item(in_memory_db, code="NVL02")
    svc.save(2026, [
        _ob(2026, "152", "NVL01", qty="100", value="5000000"),
        _ob(2026, "152", "NVL02", qty="10", value="1000000"),
        _ob(2026, "331", credit="2000000"),  # account-level credit
    ])
    net = svc.account_openings(2026)
    assert net["152"] == Decimal("6000000")
    assert net["331"] == Decimal("-2000000")


def test_baseline_before_respects_fiscal_year(in_memory_db):
    svc = _service(in_memory_db)
    _seed_item(in_memory_db)
    svc.save(2026, [_ob(2026, "152", "NVL01", qty="100", value="5000000")])
    # In effect for any date on/after 01/01/2026.
    assert svc.baseline_before(date(2026, 1, 1))["152"] == Decimal("5000000")
    # Not yet in effect before 2026.
    assert "152" not in svc.baseline_before(date(2025, 12, 31))


def test_baseline_before_uses_latest_year_only(in_memory_db):
    """Khai đầu kỳ nhiều năm: chỉ lấy năm gần nhất, không cộng đôi."""
    svc = _service(in_memory_db)
    svc.save(2026, [_ob(2026, "131", debit="10000000")])
    svc.save(2027, [_ob(2027, "131", debit="30000000")])
    # Trong 2027 chỉ tính đầu kỳ 2027 (đã bao gồm luỹ kế tới hết 2026).
    assert svc.baseline_before(date(2027, 6, 1))["131"] == Decimal("30000000")
    # Trong 2026 vẫn là đầu kỳ 2026.
    assert svc.baseline_before(date(2026, 6, 1))["131"] == Decimal("10000000")


def test_save_pushes_opening_to_inventory_nxt(in_memory_db):
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from domain.services.inventory_service import InventoryService

    svc = _service(in_memory_db)
    _seed_item(in_memory_db)
    svc.save(2026, [_ob(2026, "152", "NVL01", qty="100", value="5000000")])

    inventory = InventoryService(
        InventoryRepository(in_memory_db), ItemRepository(in_memory_db)
    )
    rows = inventory.compute_nxt(date(2026, 1, 1), date(2026, 12, 31))
    assert len(rows) == 1
    assert rows[0].opening_qty == Decimal("100")
    assert rows[0].opening_value == Decimal("5000000")


def test_save_replaces_inventory_push(in_memory_db):
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from domain.services.inventory_service import InventoryService

    svc = _service(in_memory_db)
    _seed_item(in_memory_db)
    svc.save(2026, [_ob(2026, "152", "NVL01", qty="100", value="5000000")])
    svc.save(2026, [_ob(2026, "152", "NVL01", qty="30", value="1500000")])

    inventory = InventoryService(
        InventoryRepository(in_memory_db), ItemRepository(in_memory_db)
    )
    assert inventory.on_hand("NVL01") == Decimal("30")
