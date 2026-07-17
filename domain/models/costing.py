"""Bảng tính giá thành sản phẩm (product-costing worksheet).

Costing method, taken from the blue field notes on the source form:

  * "Định mức → tính ra số tiền NVL của TP + Tương ứng + GCNK + CP khác" —
    a product's total cost (giá thành) is its direct material (NVL) plus three
    allocated pools: labor / tương ứng (15402), production overhead (154032)
    and other costs (154033).
  * "Tương ứng sp tính theo tỷ lệ NVL" — each non-material pool is split across
    products *in proportion to their direct-material amount*:

        allocated_pool_p = pool_total × (NVL_p / Σ NVL)

  * "1 cái = tổng giá thành / số lượng" — unit cost is the product's total cost
    divided by quantity produced.

Account map (sub-accounts of 154 — chi phí SXKD dở dang):
    15401 NVL trực tiếp · 15402 nhân công/tương ứng · 154032 SX chung · 154033 khác.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

_ZERO = Decimal("0")


@dataclass(frozen=True)
class CostPools:
    """The three non-material cost pools shared by the whole sheet."""

    labor: Decimal = _ZERO       # 15402 — nhân công / chi phí tương ứng
    overhead: Decimal = _ZERO    # 154032 — chi phí sản xuất chung
    other: Decimal = _ZERO       # 154033 — chi phí khác

    @property
    def total(self) -> Decimal:
        return self.labor + self.overhead + self.other


@dataclass
class CostingInput:
    """One finished product's raw inputs (the columns the user types)."""

    code: str
    name: str = ""
    quantity: Decimal = field(default_factory=lambda: _ZERO)
    material_cost: Decimal = field(default_factory=lambda: _ZERO)  # 15401 NVL

    @property
    def is_empty(self) -> bool:
        return not self.code.strip() and not self.quantity and not self.material_cost


@dataclass
class CostingRow:
    """A product after allocation — the cost breakdown the report shows."""

    code: str
    name: str
    quantity: Decimal
    material_cost: Decimal   # 15401
    labor_cost: Decimal      # 15402 (allocated)
    overhead_cost: Decimal   # 154032 (allocated)
    other_cost: Decimal      # 154033 (allocated)

    @property
    def total_cost(self) -> Decimal:
        """Tổng giá thành = NVL + nhân công + SX chung + khác."""
        return (
            self.material_cost + self.labor_cost
            + self.overhead_cost + self.other_cost
        )

    @property
    def unit_cost(self) -> Decimal:
        """Giá thành đơn vị (154/Sp) — total ÷ quantity, 0 when no quantity."""
        if self.quantity == _ZERO:
            return _ZERO
        return (self.total_cost / self.quantity).quantize(Decimal("1"))

    def unit_of(self, component: Decimal) -> Decimal:
        """A per-unit cost component (15401/sp, 15402/sp, …)."""
        if self.quantity == _ZERO:
            return _ZERO
        return (component / self.quantity).quantize(Decimal("1"))


@dataclass
class CostingSheet:
    period_key: str
    pools: CostPools
    rows: list[CostingRow] = field(default_factory=list)

    @property
    def total_quantity(self) -> Decimal:
        return sum((r.quantity for r in self.rows), _ZERO)

    @property
    def total_material(self) -> Decimal:
        return sum((r.material_cost for r in self.rows), _ZERO)

    @property
    def total_labor(self) -> Decimal:
        return sum((r.labor_cost for r in self.rows), _ZERO)

    @property
    def total_overhead(self) -> Decimal:
        return sum((r.overhead_cost for r in self.rows), _ZERO)

    @property
    def total_other(self) -> Decimal:
        return sum((r.other_cost for r in self.rows), _ZERO)

    @property
    def grand_total(self) -> Decimal:
        return sum((r.total_cost for r in self.rows), _ZERO)
