"""Business rules for item (material/tool/good) directory."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from data.repositories.item_repo import ItemRepository
from domain.models.item import Item, ItemCategory

_ALLOWED_VAT = {Decimal("0"), Decimal("5"), Decimal("8"), Decimal("10")}


class ItemValidationError(ValueError):
    pass


class ItemService:
    def __init__(self, repo: ItemRepository) -> None:
        self._repo = repo

    def list_all(self, category: ItemCategory | None = None) -> list[Item]:
        return self._repo.list_all(category)

    def search(self, query: str) -> list[Item]:
        return self._repo.search(query.strip())

    def create(self, item: Item) -> Item:
        self._validate(item)
        if self._repo.find_by_code(item.code):
            raise ItemValidationError(f"Mã '{item.code}' đã tồn tại.")
        item.created_at = datetime.now()
        item.updated_at = item.created_at
        return self._repo.insert(item)

    def update(self, item: Item) -> Item:
        if item.id is None:
            raise ItemValidationError("Không thể cập nhật vật tư chưa được lưu.")
        self._validate(item)
        # Mã vật tư có thể sửa — chặn trùng với một mặt hàng khác.
        existing = self._repo.find_by_code(item.code)
        if existing is not None and existing.id != item.id:
            raise ItemValidationError(f"Mã '{item.code}' đã tồn tại.")
        item.updated_at = datetime.now()
        return self._repo.update(item)

    def delete(self, item: Item) -> None:
        if item.id is None:
            raise ItemValidationError("Không thể xóa vật tư chưa được lưu.")
        self._repo.delete(item.id)

    @staticmethod
    def _validate(item: Item) -> None:
        if not item.code.strip():
            raise ItemValidationError("Mã vật tư là bắt buộc.")
        if not item.name.strip():
            raise ItemValidationError("Tên vật tư là bắt buộc.")
        if item.unit_price < 0:
            raise ItemValidationError("Đơn giá không được âm.")
        if item.vat_rate not in _ALLOWED_VAT:
            raise ItemValidationError("Thuế VAT phải là 0%, 5%, 8% hoặc 10%.")
