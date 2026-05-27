"""Item: vật tư / hàng hóa / công cụ theo TT200."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum


class ItemCategory(str, Enum):
    """Tài khoản kho theo TT200."""
    MATERIAL = "152"   # Nguyên vật liệu
    TOOL = "153"       # Công cụ dụng cụ
    PRODUCT = "155"    # Thành phẩm
    GOOD = "156"       # Hàng hóa


@dataclass
class Item:
    code: str
    name: str
    category: ItemCategory = ItemCategory.MATERIAL
    unit: str = "Cái"
    unit_price: Decimal = field(default_factory=lambda: Decimal("0"))
    vat_rate: Decimal = field(default_factory=lambda: Decimal("10"))
    account_code: str = ""
    notes: str = ""
    active: bool = True
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if not self.account_code:
            self.account_code = self.category.value
