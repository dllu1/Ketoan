"""Bảng tính NVL trực tiếp (ma trận SP × NVL) + đơn giá thành phần giá thành.

Kiểm hai phần vừa thêm để dựng lại hai tờ in của Hưng Phát:
  * ``BomService.material_matrix`` — chi tiết cột 15401 theo từng loại NVL.
  * ``CostingRow`` — các đơn giá thành phần 15401/sp · 15402/sp · 15403/sp.
"""
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


def _bom(conn):
    from data.repositories.bom_repo import BomRepository
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from domain.services.bom_service import BomService
    from domain.services.inventory_service import InventoryService

    inventory = InventoryService(InventoryRepository(conn), ItemRepository(conn))
    return BomService(BomRepository(conn), inventory, ItemRepository(conn))


def _seed_item(conn, code, category, unit_price="0", name=None):
    from data.repositories.item_repo import ItemRepository
    from domain.models.item import Item, ItemCategory

    ItemRepository(conn).insert(
        Item(code=code, name=name or f"Mặt hàng {code}",
             category=ItemCategory(category), unit="kg", unit_price=Decimal(unit_price))
    )


def _line(product, material, qty):
    from domain.models.bom import BomLine

    return BomLine(product_code=product, material_code=material,
                   quantity_per=Decimal(qty))


# ----- material matrix -----------------------------------------------------


def test_matrix_breaks_direct_material_by_type(in_memory_db):
    svc = _bom(in_memory_db)
    _seed_item(in_memory_db, "TP01", "155")
    _seed_item(in_memory_db, "SAT3", "152", unit_price="10000", name="Sắt tấm 3")
    _seed_item(in_memory_db, "CHI", "152", unit_price="5000", name="Chì")
    svc.save("TP01", [_line("TP01", "SAT3", "2"), _line("TP01", "CHI", "3")])

    matrix = svc.material_matrix([("TP01", "Thành phẩm 01", Decimal("10"))])

    assert matrix.materials == ["CHI", "SAT3"]  # sắp theo mã
    row = matrix.rows[0]
    # SAT3: 2 × 10 × 10000 = 200000 ; CHI: 3 × 10 × 5000 = 150000
    assert row.value_of("SAT3") == Decimal("200000")
    assert row.value_of("CHI") == Decimal("150000")
    assert row.total_value == Decimal("350000")


def test_matrix_total_value_matches_bom_material_cost(in_memory_db):
    """Cột "Cộng" mỗi SP phải khớp material_cost (cột 15401 bên giá thành)."""
    svc = _bom(in_memory_db)
    _seed_item(in_memory_db, "TP01", "155")
    _seed_item(in_memory_db, "NVL01", "152", unit_price="10000")
    _seed_item(in_memory_db, "NVL02", "152", unit_price="5000")
    svc.save("TP01", [_line("TP01", "NVL01", "2"), _line("TP01", "NVL02", "3")])

    qty = Decimal("10")
    matrix = svc.material_matrix([("TP01", "TP", qty)])
    assert matrix.rows[0].total_value == svc.material_cost("TP01", qty)


def test_matrix_columns_are_union_across_products(in_memory_db):
    svc = _bom(in_memory_db)
    _seed_item(in_memory_db, "TP01", "155")
    _seed_item(in_memory_db, "TP02", "155")
    _seed_item(in_memory_db, "SAT3", "152", unit_price="10000")
    _seed_item(in_memory_db, "CHI", "152", unit_price="5000")
    _seed_item(in_memory_db, "NHOM", "152", unit_price="8000")
    svc.save("TP01", [_line("TP01", "SAT3", "1"), _line("TP01", "CHI", "1")])
    svc.save("TP02", [_line("TP02", "SAT3", "1"), _line("TP02", "NHOM", "1")])

    matrix = svc.material_matrix([
        ("TP01", "TP01", Decimal("1")),
        ("TP02", "TP02", Decimal("1")),
    ])
    # Cột = hợp của mọi NVL; ô không dùng thì giá trị 0.
    assert matrix.materials == ["CHI", "NHOM", "SAT3"]
    assert matrix.rows[0].value_of("NHOM") == Decimal("0")
    assert matrix.rows[1].value_of("CHI") == Decimal("0")


def test_matrix_material_totals_and_unit_price(in_memory_db):
    svc = _bom(in_memory_db)
    _seed_item(in_memory_db, "TP01", "155")
    _seed_item(in_memory_db, "TP02", "155")
    _seed_item(in_memory_db, "SAT3", "152", unit_price="10000")
    svc.save("TP01", [_line("TP01", "SAT3", "2")])
    svc.save("TP02", [_line("TP02", "SAT3", "3")])

    matrix = svc.material_matrix([
        ("TP01", "TP01", Decimal("10")),   # 20 kg
        ("TP02", "TP02", Decimal("10")),   # 30 kg
    ])
    assert matrix.material_qty("SAT3") == Decimal("50")
    assert matrix.material_value("SAT3") == Decimal("500000")
    assert matrix.unit_prices["SAT3"] == Decimal("10000")
    assert matrix.grand_total == Decimal("500000")


def test_matrix_skips_products_without_bom_or_quantity(in_memory_db):
    svc = _bom(in_memory_db)
    _seed_item(in_memory_db, "TP01", "155")
    _seed_item(in_memory_db, "SAT3", "152", unit_price="10000")
    svc.save("TP01", [_line("TP01", "SAT3", "1")])

    matrix = svc.material_matrix([
        ("TP01", "TP01", Decimal("0")),      # SL 0 → không tiêu hao
        ("TPX", "Chưa có định mức", Decimal("5")),
    ])
    assert matrix.materials == []
    assert all(r.total_value == Decimal("0") for r in matrix.rows)


# ----- costing unit components ---------------------------------------------


def test_costing_row_unit_components_sum_and_group():
    from domain.models.costing import CostingRow

    row = CostingRow(
        code="TP01", name="TP", quantity=Decimal("100"),
        material_cost=Decimal("500000"), labor_cost=Decimal("200000"),
        overhead_cost=Decimal("120000"), other_cost=Decimal("80000"),
    )
    assert row.unit_material == Decimal("5000")           # 15401/sp
    assert row.unit_labor == Decimal("2000")              # 15402/sp
    assert row.unit_overhead_other == Decimal("2000")     # 15403/sp = (120k+80k)/100
    assert row.unit_components_sum == Decimal("9000")     # 154/Sp cột đơn giá
    assert row.unit_cost == Decimal("9000")               # 154/Sp = tổng/SL


def test_costing_row_unit_components_zero_when_no_quantity():
    from domain.models.costing import CostingRow

    row = CostingRow(
        code="TP01", name="TP", quantity=Decimal("0"),
        material_cost=Decimal("500000"), labor_cost=Decimal("0"),
        overhead_cost=Decimal("0"), other_cost=Decimal("0"),
    )
    assert row.unit_material == Decimal("0")
    assert row.unit_components_sum == Decimal("0")
