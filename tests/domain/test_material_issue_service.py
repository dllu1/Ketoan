"""MaterialIssueService tests — xuất NVL theo giá thành trừ vào kho 152.

Verifies: NVL consumption is decomposed by material code from the BOM, priced at
the period weighted-average issue price (bình quân gia quyền, như thành phẩm),
issued from 152 as OUT movements that show up in Nhập–Xuất–Tồn, and re-posting
refreshes rather than stacks. Also that the Bảng kê NVL chính is not corrupted by
these costing-driven movements.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

_FROM, _TO = date(2026, 1, 1), date(2026, 12, 31)


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


def _seed_item(conn, code, category, unit_price="0"):
    from data.repositories.item_repo import ItemRepository
    from domain.models.item import Item, ItemCategory

    ItemRepository(conn).insert(
        Item(code=code, name=f"Mặt hàng {code}", category=ItemCategory(category),
             unit="kg", unit_price=Decimal(unit_price))
    )


def _services(conn):
    from data.repositories.bom_repo import BomRepository
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from domain.services.bom_service import BomService
    from domain.services.inventory_service import InventoryService
    from domain.services.material_issue_service import MaterialIssueService

    items = ItemRepository(conn)
    inventory = InventoryService(InventoryRepository(conn), items)
    bom = BomService(BomRepository(conn), inventory, items)
    issue = MaterialIssueService(inventory, bom, items)
    return issue, inventory, bom


def _line(product, material, qty):
    from domain.models.bom import BomLine
    return BomLine(product_code=product, material_code=material,
                   quantity_per=Decimal(qty))


def _nxt(inventory):
    return {r.item_code: r for r in inventory.compute_nxt(_FROM, _TO)}


def test_consumption_issued_from_152_by_material_code(in_memory_db):
    issue, inventory, bom = _services(in_memory_db)
    _seed_item(in_memory_db, "TP01", "155")
    _seed_item(in_memory_db, "NVL01", "152")
    _seed_item(in_memory_db, "NVL02", "152")
    # Nhập tồn NVL để có đơn giá bình quân: NVL01 = 12,000/kg, NVL02 = 5,000/kg.
    inventory.record_in("NVL01", Decimal("100"), Decimal("12000"),
                        move_date=date(2026, 1, 5))
    inventory.record_in("NVL02", Decimal("100"), Decimal("5000"),
                        move_date=date(2026, 1, 5))
    bom.save("TP01", [_line("TP01", "NVL01", "2"), _line("TP01", "NVL02", "3")])

    consumed = issue.post("2026", [("TP01", Decimal("10"))])

    # SL xuất mỗi NVL = định mức × SL sản xuất; TT = SL × ĐG xuất bình quân.
    assert consumed["NVL01"] == (Decimal("20"), Decimal("240000"))
    assert consumed["NVL02"] == (Decimal("30"), Decimal("150000"))

    nxt = _nxt(inventory)
    assert nxt["NVL01"].out_qty == Decimal("20")
    assert nxt["NVL01"].out_value == Decimal("240000")
    assert nxt["NVL01"].closing_qty == Decimal("80")   # 100 nhập − 20 xuất
    assert nxt["NVL02"].out_qty == Decimal("30")


def test_issue_price_is_weighted_average_of_opening_plus_in(in_memory_db):
    issue, inventory, bom = _services(in_memory_db)
    _seed_item(in_memory_db, "TP01", "155")
    _seed_item(in_memory_db, "NVL01", "152")
    # Hai lần nhập giá khác nhau: bình quân = (100*10000 + 100*20000)/200 = 15000.
    inventory.record_in("NVL01", Decimal("100"), Decimal("10000"),
                        move_date=date(2026, 1, 5))
    inventory.record_in("NVL01", Decimal("100"), Decimal("20000"),
                        move_date=date(2026, 2, 5))
    bom.save("TP01", [_line("TP01", "NVL01", "1")])

    consumed = issue.post("2026", [("TP01", Decimal("50"))])
    assert consumed["NVL01"] == (Decimal("50"), Decimal("750000"))  # 50 * 15000


def test_falls_back_to_catalog_price_when_no_stock(in_memory_db):
    issue, _inventory, bom = _services(in_memory_db)
    _seed_item(in_memory_db, "TP01", "155")
    _seed_item(in_memory_db, "NVL01", "152", unit_price="8000")
    bom.save("TP01", [_line("TP01", "NVL01", "2")])

    consumed = issue.post("2026", [("TP01", Decimal("5"))])
    assert consumed["NVL01"] == (Decimal("10"), Decimal("80000"))  # 10 * 8000 catalog


def test_repost_is_idempotent(in_memory_db):
    issue, inventory, bom = _services(in_memory_db)
    _seed_item(in_memory_db, "TP01", "155")
    _seed_item(in_memory_db, "NVL01", "152", unit_price="1000")
    bom.save("TP01", [_line("TP01", "NVL01", "1")])

    issue.post("2026", [("TP01", Decimal("10"))])
    issue.post("2026", [("TP01", Decimal("10"))])   # lưu lại giá thành lần nữa
    assert _nxt(inventory)["NVL01"].out_qty == Decimal("10")   # refreshed, not 20


def test_material_sheet_not_corrupted_by_costing_issue(in_memory_db):
    """A hand-tracked material consumed by costing keeps its manual row; the
    GT-NVL xuất doesn't leak in as a phantom read-only ledger row."""
    from data.repositories.material_sheet_repo import MaterialSheetRepository
    from domain.models.material_sheet import MaterialLine, MaterialSheet
    from domain.services.material_sheet_service import MaterialSheetService

    issue, inventory, bom = _services(in_memory_db)
    _seed_item(in_memory_db, "TP01", "155")
    _seed_item(in_memory_db, "NVL01", "152", unit_price="1000")
    bom.save("TP01", [_line("TP01", "NVL01", "1")])

    sheet_svc = MaterialSheetService(MaterialSheetRepository(in_memory_db), inventory)
    sheet_svc.save(MaterialSheet("2026", [
        MaterialLine(code="NVL01", name="NVL01", unit="kg",
                     in_qty=Decimal("100"), in_value=Decimal("100000")),
    ]))
    issue.post("2026", [("TP01", Decimal("10"))])

    loaded = sheet_svc.load("2026")
    nvl_rows = [ln for ln in loaded.lines if ln.code == "NVL01"]
    assert len(nvl_rows) == 1
    assert nvl_rows[0].from_ledger is False       # vẫn là dòng nhập tay
    assert nvl_rows[0].in_qty == Decimal("100")   # không bị GT-NVL ghi đè
