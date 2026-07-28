"""Business rules for item (material/tool/good) directory."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from data.repositories.item_repo import ItemRepository
from domain.models.item import Item, ItemCategory

_ALLOWED_VAT = {Decimal("0"), Decimal("5"), Decimal("8"), Decimal("10")}

_STOCK_CATEGORIES = {c.value: c for c in ItemCategory}   # "152" → MATERIAL, …


def _category_for_account(account_code: str) -> ItemCategory:
    """Nhóm hàng theo 3 số đầu của TK kho; mặc định NVL (152) nếu TK lạ."""
    return _STOCK_CATEGORIES.get((account_code or "")[:3], ItemCategory.MATERIAL)


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

    def import_stock_items(
        self, items: Iterable[tuple[str, str, str, str]]
    ) -> int:
        """Tạo mặt hàng trong danh mục cho các mã kho được chọn; trả về số mã mới.

        ``items`` là ``(mã, tên, ĐVT, TK kho)`` — thường lấy từ sổ kho. Nhóm hàng
        (152/153/155/156) suy từ TK kho, mặc định NVL (152) nếu TK lạ. Mã đã có
        trong danh mục được **bỏ qua** (giữ nguyên thông tin đã khai tay).
        """
        created = 0
        for code, name, unit, account_code in items:
            code = (code or "").strip()
            if not code or self._repo.find_by_code(code):
                continue
            self.create(Item(
                code=code,
                name=(name or "").strip() or code,
                category=_category_for_account(account_code),
                unit=(unit or "").strip() or "Cái",
            ))
            created += 1
        return created

    def import_materials(self, materials: Iterable[tuple[str, str, str]]) -> int:
        """Tạo NVL (152) trong danh mục cho các mã chưa có; trả về số mã mới tạo.

        ``materials`` là ``(mã, tên, ĐVT)`` — thường lấy từ sổ kho NVL. Mã đã tồn
        tại trong danh mục được **bỏ qua** (không ghi đè) để giữ nguyên đơn giá /
        VAT / tài khoản người dùng đã khai tay. Nhờ vậy kế toán không phải nhập
        lại toàn bộ NVL đã có trong kho hàng.
        """
        created = 0
        for code, name, unit in materials:
            code = (code or "").strip()
            if not code or self._repo.find_by_code(code):
                continue
            self.create(Item(
                code=code,
                name=(name or "").strip() or code,
                category=ItemCategory.MATERIAL,
                unit=(unit or "").strip() or "Cái",
            ))
            created += 1
        return created

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
