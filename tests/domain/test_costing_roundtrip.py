"""Hồi quy cho vòng Bảng kê TP (155) ↔ Giá thành SP ↔ Bảng kê NVL chính.

Hai lỗi từng gặp, không được tái phát:

* Lưu bảng giá thành làm **số lượng thành phẩm nhân đôi** — vì bảng giá thành tự
  đẩy một bút toán nhập kho 155 riêng, cộng chồng lên phần Bảng kê TP đã đẩy.
* Lưu bảng giá thành xong, **Bảng kê NVL chính không đổi gì** — phần xuất NVL
  theo định mức bị lọc khỏi bảng.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.models.product_sheet import ProductLine, ProductSheet


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


PK = "2026"


@pytest.fixture
def world(in_memory_db):
    """Kho có 36.122 kg thép S20; thành phẩm N12 định mức 2 kg/cái."""
    from data.repositories.bom_repo import BomRepository
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from data.repositories.material_sheet_repo import MaterialSheetRepository
    from data.repositories.product_sheet_repo import ProductSheetRepository
    from domain.models.bom import BomLine
    from domain.models.item import Item, ItemCategory
    from domain.services.bom_service import BomService
    from domain.services.inventory_service import InventoryService
    from domain.services.material_issue_service import MaterialIssueService
    from domain.services.material_sheet_service import MaterialSheetService
    from domain.services.product_sheet_service import ProductSheetService

    conn = in_memory_db
    items = ItemRepository(conn)
    items.insert(Item(code="N12", name="Ty 25x30", category=ItemCategory("155"),
                      unit="Cái"))
    items.insert(Item(code="S20", name="Thép phi 20", category=ItemCategory("152"),
                      unit="kg", unit_price=Decimal("15364")))

    inventory = InventoryService(InventoryRepository(conn), items)
    inventory.record_in("S20", Decimal("36122"), Decimal("15364"),
                        move_date=date(2026, 1, 1), account_code="152")

    bom = BomService(BomRepository(conn), inventory, items)
    bom.save("N12", [BomLine(product_code="N12", material_code="S20",
                             quantity_per=Decimal("2"))])

    return {
        "conn": conn,
        "product": ProductSheetService(ProductSheetRepository(conn),
                                       inventory=inventory, item_repo=items),
        "material": MaterialSheetService(MaterialSheetRepository(conn),
                                         inventory=inventory, item_repo=items),
        "issue": MaterialIssueService(inventory=inventory, bom=bom, item_repo=items),
    }


def _tp_line(world, code="N12"):
    return next(ln for ln in world["product"].load(PK).lines if ln.code == code)


def _nvl_line(world, code="S20"):
    return next(ln for ln in world["material"].load(PK).lines if ln.code == code)


# ----- số lượng thành phẩm không được đổi khi lưu giá thành ------------------


def test_saving_costing_does_not_change_finished_goods_quantity(world):
    world["product"].save(ProductSheet(period_key=PK, lines=[
        ProductLine(code="N12", name="Ty", unit="Cái", in_qty=Decimal("1260")),
    ]))
    world["issue"].post(PK, [("N12", Decimal("1260"))])

    line = _tp_line(world)
    assert line.in_qty == Decimal("1260")        # không nhân đôi
    assert not line.from_ledger                  # vẫn là dòng sửa được


def test_saving_costing_twice_keeps_quantity_stable(world):
    world["product"].save(ProductSheet(period_key=PK, lines=[
        ProductLine(code="N12", name="Ty", unit="Cái", in_qty=Decimal("1260")),
    ]))
    for _ in range(3):
        world["issue"].post(PK, [("N12", Decimal("1260"))])

    assert _tp_line(world).in_qty == Decimal("1260")
    assert world["product"].input_quantities(PK) == [("N12", "Ty", Decimal("1260"))]


# ----- NVL phải hiện phần xuất theo định mức --------------------------------


def test_material_sheet_shows_costing_consumption(world):
    """2 kg/cái × 1.260 cái = 2.520 kg phải hiện ở cột Xuất của bảng kê NVL."""
    assert _nvl_line(world).total_out_qty == Decimal("0")

    world["issue"].post(PK, [("N12", Decimal("1260"))])

    after = _nvl_line(world)
    assert after.issued_qty == Decimal("2520")
    assert after.total_out_qty == Decimal("2520")
    assert after.closing_qty == Decimal("36122") - Decimal("2520")


def test_costing_consumption_is_not_persisted_as_manual_out(world):
    """Phần xuất theo giá thành đã ở sổ kho — lưu bảng kê không được đẩy lại."""
    from data.repositories.material_sheet_repo import MaterialSheetRepository

    world["issue"].post(PK, [("N12", Decimal("1260"))])
    world["material"].save(world["material"].load(PK))

    # Dòng lưu xuống không mang phần issued (nếu mang thì kho bị trừ hai lần).
    saved = MaterialSheetRepository(world["conn"]).list_for_period(PK)
    assert all(ln.out_qty == Decimal("0") for ln in saved)
    # Và số hiển thị vẫn đúng sau khi lưu.
    assert _nvl_line(world).total_out_qty == Decimal("2520")


# ----- giá thành đẩy ngược: chỉ đơn giá, không đụng số lượng ----------------


def _nxt(world, code="N12"):
    inventory = world["material"]._inventory
    rows = inventory.compute_nxt(date(2026, 1, 1), date(2026, 12, 31))
    return next(r for r in rows if r.item_code == code)


def test_each_stock_in_adds_a_quantity_the_costing_sheet_sees(world):
    """Nhập kho thêm bao nhiêu thì bảng giá thành thấy bấy nhiêu."""
    inventory = world["material"]._inventory
    inventory.record_in("N12", Decimal("1260"), Decimal("0"),
                        move_date=date(2026, 3, 5), account_code="155")
    assert world["product"].input_quantities(PK) == [
        ("N12", "Ty 25x30", Decimal("1260"))
    ]

    inventory.record_in("N12", Decimal("500"), Decimal("0"),
                        move_date=date(2026, 6, 9), account_code="155")
    assert world["product"].input_quantities(PK) == [
        ("N12", "Ty 25x30", Decimal("1760"))
    ]


def test_reprice_sets_unit_cost_without_touching_quantity(world):
    inventory = world["material"]._inventory
    inventory.record_in("N12", Decimal("1260"), Decimal("0"),
                        move_date=date(2026, 3, 5), account_code="155")

    world["issue"].reprice_finished_goods(
        PK, [("N12", Decimal("1260"), Decimal("29661"))]
    )

    row = _nxt(world)
    assert row.in_qty == Decimal("1260")        # số lượng nguyên vẹn
    assert row.in_price == Decimal("29661")     # đơn giá = giá thành đơn vị


def test_repricing_again_replaces_the_price_and_never_stacks_quantity(world):
    """Lưu giá thành lần hai (lương về trễ) chỉ đổi giá, không cộng lượng."""
    inventory = world["material"]._inventory
    inventory.record_in("N12", Decimal("1260"), Decimal("0"),
                        move_date=date(2026, 3, 5), account_code="155")

    world["issue"].reprice_finished_goods(
        PK, [("N12", Decimal("1260"), Decimal("29661"))]
    )
    world["issue"].reprice_finished_goods(
        PK, [("N12", Decimal("1260"), Decimal("31000"))]
    )

    row = _nxt(world)
    assert row.in_qty == Decimal("1260")
    assert row.in_price == Decimal("31000")


def test_reissuing_does_not_stack_consumption(world):
    """GT-NVL idempotent: chạy lại vẫn 2.520 kg, không cộng dồn."""
    for _ in range(3):
        world["issue"].post(PK, [("N12", Decimal("1260"))])

    assert _nvl_line(world).total_out_qty == Decimal("2520")
