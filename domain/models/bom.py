"""Định mức nguyên vật liệu (bill of materials) for finished products.

One :class:`BomLine` per material that goes into a finished product, recording
the standard quantity consumed per unit produced (``quantity_per``). The costing
worksheet multiplies this by the produced quantity and the material's unit cost
to derive the direct-material (NVL, 15401) column.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

_ZERO = Decimal("0")


@dataclass
class BomLine:
    product_code: str
    material_code: str
    material_name: str = ""
    unit: str = ""
    quantity_per: Decimal = field(default_factory=lambda: _ZERO)
    note: str = ""
    # Quy cách đóng gói: số thành phẩm mà 1 đơn vị NVL bao được (vd 1 thùng
    # carton chứa 25 cây → 25). Khi > 0, ``quantity_per`` được suy ra = 1/N để
    # người dùng khỏi tự tính phân số. Bằng 0 = nhập định mức trực tiếp.
    pieces_per_pack: Decimal = field(default_factory=lambda: _ZERO)
    id: int | None = None

    @property
    def is_empty(self) -> bool:
        return not self.material_code.strip() and not self.quantity_per

    def apply_packaging(self) -> None:
        """Suy ra định mức/1 thành phẩm từ quy cách đóng gói (nếu có khai)."""
        if self.pieces_per_pack and self.pieces_per_pack > _ZERO:
            self.quantity_per = Decimal(1) / self.pieces_per_pack


@dataclass
class Bom:
    product_code: str
    lines: list[BomLine] = field(default_factory=list)
