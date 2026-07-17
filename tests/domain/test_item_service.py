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
