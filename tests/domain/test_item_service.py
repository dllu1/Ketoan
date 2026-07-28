"""ItemService tests — directory CRUD incl. editable code + delete."""
from __future__ import annotations

from decimal import Decimal  # noqa: F401 — kept for parity with sibling tests

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
    from data.repositories.item_repo import ItemRepository
    from domain.services.item_service import ItemService

    return ItemService(ItemRepository(conn))


def _item(code="S20", name="Sắt phi 20"):
    from domain.models.item import Item, ItemCategory

    return Item(code=code, name=name, category=ItemCategory.MATERIAL, unit="kg")


def test_create_then_delete_removes_item(in_memory_db):
    service = _service(in_memory_db)
    saved = service.create(_item())
    assert any(i.code == "S20" for i in service.list_all())

    service.delete(saved)
    assert all(i.code != "S20" for i in service.list_all())


def test_update_can_change_code(in_memory_db):
    service = _service(in_memory_db)
    saved = service.create(_item(code="s20"))
    saved.code = "S20"
    saved.name = "Sắt phi 20 (sửa)"
    service.update(saved)

    codes = {i.code for i in service.list_all()}
    assert "S20" in codes and "s20" not in codes


def test_update_rejects_duplicate_code(in_memory_db):
    from domain.services.item_service import ItemValidationError

    service = _service(in_memory_db)
    service.create(_item(code="S20", name="Sắt phi 20"))
    other = service.create(_item(code="S30", name="Sắt phi 30"))

    other.code = "S20"   # đụng mã của mặt hàng đã có
    with pytest.raises(ItemValidationError):
        service.update(other)


def test_delete_unsaved_item_raises(in_memory_db):
    from domain.services.item_service import ItemValidationError

    service = _service(in_memory_db)
    with pytest.raises(ItemValidationError):
        service.delete(_item())   # chưa có id


def test_import_materials_creates_missing_as_152(in_memory_db):
    from domain.models.item import ItemCategory

    service = _service(in_memory_db)
    created = service.import_materials([
        ("NVL01", "Sắt tấm", "Kg"),
        ("NVL02", "Sơn", "Lít"),
    ])
    assert created == 2
    by_code = {i.code: i for i in service.list_all()}
    assert by_code["NVL01"].name == "Sắt tấm"
    assert by_code["NVL01"].category is ItemCategory.MATERIAL
    assert by_code["NVL01"].unit == "Kg"


def test_import_materials_skips_existing_without_overwriting(in_memory_db):
    from decimal import Decimal

    from domain.models.item import Item, ItemCategory

    service = _service(in_memory_db)
    # Đã khai tay với đơn giá riêng — không được ghi đè khi lấy từ kho.
    service.create(Item(code="NVL01", name="Sắt tấm (đã khai)",
                        category=ItemCategory.MATERIAL, unit="Kg",
                        unit_price=Decimal("25000")))

    created = service.import_materials([
        ("NVL01", "Sắt tấm (kho)", "Tấn"),   # trùng mã → bỏ qua
        ("NVL09", "Keo", "Hộp"),             # mới → tạo
    ])
    assert created == 1
    kept = next(i for i in service.list_all() if i.code == "NVL01")
    assert kept.name == "Sắt tấm (đã khai)"
    assert kept.unit == "Kg"
    assert kept.unit_price == Decimal("25000")


def test_import_materials_defaults_blank_name_and_unit(in_memory_db):
    service = _service(in_memory_db)
    service.import_materials([("NVL03", "", "")])
    item = next(i for i in service.list_all() if i.code == "NVL03")
    assert item.name == "NVL03"   # tên trống → dùng mã
    assert item.unit == "Cái"     # ĐVT trống → mặc định


def test_import_stock_items_maps_category_from_account(in_memory_db):
    from domain.models.item import ItemCategory

    service = _service(in_memory_db)
    created = service.import_stock_items([
        ("VT01", "Thép", "Kg", "152"),
        ("CC01", "Kìm", "Cái", "153"),
        ("TP01", "Bàn", "Cái", "155"),
        ("HH01", "Ốc vít", "Hộp", "156"),
        ("LA01", "Lạ", "Cái", "331"),   # TK lạ → mặc định NVL
    ])
    assert created == 5
    by_code = {i.code: i for i in service.list_all()}
    assert by_code["VT01"].category is ItemCategory.MATERIAL
    assert by_code["CC01"].category is ItemCategory.TOOL
    assert by_code["TP01"].category is ItemCategory.PRODUCT
    assert by_code["HH01"].category is ItemCategory.GOOD
    assert by_code["LA01"].category is ItemCategory.MATERIAL


def test_import_stock_items_skips_existing(in_memory_db):
    service = _service(in_memory_db)
    service.create(_item(code="VT01", name="Thép (đã khai)"))
    created = service.import_stock_items([
        ("VT01", "Thép (kho)", "Tấn", "152"),   # trùng → bỏ qua
        ("VT02", "Nhôm", "Kg", "152"),          # mới
    ])
    assert created == 1
    assert next(i for i in service.list_all() if i.code == "VT01").name == "Thép (đã khai)"
