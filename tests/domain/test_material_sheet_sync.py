"""Two-way link between Bảng kê NVL chính and the Nhập–Xuất–Tồn ledger.

Verifies the requirement that materials on the worksheet show up in the NXT
report and vice versa, *without* double-counting real mua/bán movements:

* a manual material saved on the sheet is pushed into the ledger → appears in NXT;
* a material that already has real document movements is pulled into the sheet
  read-only and is never re-pushed (no double count);
* re-saving is idempotent (refresh, not stack).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.models.material_sheet import MaterialLine, MaterialSheet

_FROM, _TO = date(2026, 1, 1), date(2026, 12, 31)


@pytest.fixture
def db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.config.DB_PATH", db_file)
    monkeypatch.setattr("data.database.DB_PATH", db_file)
    import data.database as db_mod
    db_mod._conn = None
    db_mod.init_database()
    yield db_mod.get_connection()
    db_mod.close_connection()


def _services():
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from data.repositories.material_sheet_repo import MaterialSheetRepository
    from domain.services.inventory_service import InventoryService
    from domain.services.material_sheet_service import MaterialSheetService

    inventory = InventoryService(InventoryRepository(), ItemRepository())
    service = MaterialSheetService(MaterialSheetRepository(), inventory)
    return service, inventory


def _nxt(inventory):
    return {r.item_code: r for r in inventory.compute_nxt(_FROM, _TO)}


def test_manual_material_is_pushed_into_nxt(db):
    service, inventory = _services()
    service.save(MaterialSheet("2026", [
        MaterialLine(
            code="NVL-X", name="Bột màu X", unit="Kg",
            opening_qty=Decimal(100), opening_value=Decimal(1_000_000),
            in_qty=Decimal(50), in_value=Decimal(600_000),
            out_qty=Decimal(30), out_value=Decimal(360_000),
        ),
    ]))
    row = _nxt(inventory)["NVL-X"]
    assert row.opening_qty == Decimal(100)
    assert row.in_qty == Decimal(50)
    assert row.out_qty == Decimal(30)
    assert row.closing_qty == Decimal(120)
    assert row.account_code == "152"   # đứng nhóm Nguyên vật liệu


def test_ledger_material_appears_readonly_and_is_not_double_counted(db):
    from data.repositories.item_repo import ItemRepository
    from domain.models.item import Item, ItemCategory

    service, inventory = _services()
    ItemRepository().insert(Item(
        code="VT1", name="Que hàn", category=ItemCategory.MATERIAL, unit="Kg",
    ))
    inventory.record_in(
        "VT1", Decimal(200), Decimal(35_000),
        move_date=date(2026, 3, 1), source_ref="PN001",
    )

    loaded = service.load("2026")
    vt1 = [ln for ln in loaded.lines if ln.code == "VT1"]
    assert vt1 and vt1[0].from_ledger is True
    assert vt1[0].in_qty == Decimal(200)

    # Saving the sheet (which echoes VT1 back) must not add extra movements.
    service.save(loaded)
    assert _nxt(inventory)["VT1"].in_qty == Decimal(200)   # not 400


def test_resave_is_idempotent(db):
    service, inventory = _services()
    sheet = MaterialSheet("2026", [
        MaterialLine(code="NVL-Y", name="Y", unit="Kg",
                     in_qty=Decimal(10), in_value=Decimal(100_000)),
    ])
    service.save(sheet)
    service.save(service.load("2026"))   # reload (still manual) + save again
    assert _nxt(inventory)["NVL-Y"].in_qty == Decimal(10)   # refreshed, not 20


def test_manual_material_round_trips_as_editable(db):
    service, _ = _services()
    service.save(MaterialSheet("2026", [
        MaterialLine(code="NVL-Z", name="Z", unit="Kg",
                     in_qty=Decimal(5), in_value=Decimal(50_000)),
    ]))
    loaded = service.load("2026")
    nvl_z = [ln for ln in loaded.lines if ln.code == "NVL-Z"]
    assert nvl_z and nvl_z[0].from_ledger is False   # stays sheet-owned/editable
