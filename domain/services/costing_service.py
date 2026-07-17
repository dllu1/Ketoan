"""Service for the product-costing worksheet (Bảng tính giá thành sản phẩm).

Implements the allocation rule from the form's blue notes: the labor (15402),
overhead (154032) and other (154033) pools are each distributed across products
in proportion to their direct-material (NVL) amount. Quantization can leave a
sub-đồng remainder; it is absorbed by the largest-NVL product so each allocated
column still sums *exactly* to its pool.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from domain.models.costing import (
    CostingInput,
    CostingRow,
    CostingSheet,
    CostPools,
)

_ZERO = Decimal("0")
_ONE = Decimal("1")


class CostingService:
    def __init__(self, repo=None) -> None:
        self._repo = repo

    # ----- core computation ------------------------------------------------

    def compute(self, inputs: list[CostingInput], pools: CostPools) -> CostingSheet:
        return self._build("", inputs, pools)

    def _build(
        self, period_key: str, inputs: list[CostingInput], pools: CostPools
    ) -> CostingSheet:
        total_nvl = sum((i.material_cost for i in inputs), _ZERO)
        labor = self._allocate(inputs, total_nvl, pools.labor)
        overhead = self._allocate(inputs, total_nvl, pools.overhead)
        other = self._allocate(inputs, total_nvl, pools.other)

        rows = [
            CostingRow(
                code=inp.code,
                name=inp.name,
                quantity=inp.quantity,
                material_cost=inp.material_cost,
                labor_cost=labor[idx],
                overhead_cost=overhead[idx],
                other_cost=other[idx],
            )
            for idx, inp in enumerate(inputs)
        ]
        return CostingSheet(period_key=period_key, pools=pools, rows=rows)

    @staticmethod
    def _allocate(
        inputs: list[CostingInput], total_nvl: Decimal, pool: Decimal
    ) -> list[Decimal]:
        """Split *pool* across products by NVL ratio; the sum equals *pool*."""
        n = len(inputs)
        if n == 0 or total_nvl <= _ZERO or pool == _ZERO:
            return [_ZERO] * n
        amounts = [
            (pool * inp.material_cost / total_nvl).quantize(_ONE, ROUND_HALF_UP)
            for inp in inputs
        ]
        residual = pool - sum(amounts, _ZERO)
        if residual != _ZERO:
            biggest = max(range(n), key=lambda i: inputs[i].material_cost)
            amounts[biggest] += residual
        return amounts

    # ----- persistence -----------------------------------------------------

    def load(self, period_key: str) -> CostingSheet:
        pools, inputs = self._repo.load(period_key)
        return self._build(period_key, inputs, pools)

    def save(
        self, period_key: str, inputs: list[CostingInput], pools: CostPools
    ) -> CostingSheet:
        kept = [i for i in inputs if not i.is_empty]
        self._repo.replace(period_key, pools, kept)
        return self._build(period_key, kept, pools)
