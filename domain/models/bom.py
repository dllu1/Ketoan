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
    id: int | None = None

    @property
    def is_empty(self) -> bool:
        return not self.material_code.strip() and not self.quantity_per


@dataclass
class Bom:
    product_code: str
    lines: list[BomLine] = field(default_factory=list)
