"""Repository for the product-costing worksheet.

Two tables back one document per period: ``costing_sheet`` holds the three cost
pools and ``costing_product`` holds the per-product inputs. ``load`` returns the
raw inputs (allocation is the service's job); ``replace`` rewrites both tables
for the period wholesale.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

from data.database import get_connection
from domain.models.costing import CostingInput, CostPools


class CostingRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def load(self, period_key: str) -> tuple[CostPools, list[CostingInput]]:
        sheet = self._conn.execute(
            "SELECT * FROM costing_sheet WHERE period_key = ?", (period_key,)
        ).fetchone()
        pools = CostPools(
            labor=Decimal(str(sheet["labor_pool"])),
            overhead=Decimal(str(sheet["overhead_pool"])),
            other=Decimal(str(sheet["other_pool"])),
        ) if sheet else CostPools()

        rows = self._conn.execute(
            "SELECT * FROM costing_product WHERE period_key = ? ORDER BY line_no, id",
            (period_key,),
        ).fetchall()
        inputs = [
            CostingInput(
                code=r["code"],
                name=r["name"],
                quantity=Decimal(str(r["quantity"])),
                material_cost=Decimal(str(r["material_cost"])),
            )
            for r in rows
        ]
        return pools, inputs

    def replace(
        self, period_key: str, pools: CostPools, inputs: list[CostingInput]
    ) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM costing_sheet WHERE period_key = ?", (period_key,)
            )
            self._conn.execute(
                "DELETE FROM costing_product WHERE period_key = ?", (period_key,)
            )
            self._conn.execute(
                "INSERT INTO costing_sheet (period_key, labor_pool, overhead_pool, "
                "other_pool) VALUES (?,?,?,?)",
                (period_key, str(pools.labor), str(pools.overhead), str(pools.other)),
            )
            self._conn.executemany(
                "INSERT INTO costing_product (period_key, line_no, code, name, "
                "quantity, material_cost) VALUES (?,?,?,?,?,?)",
                [
                    (
                        period_key, idx, inp.code, inp.name,
                        str(inp.quantity), str(inp.material_cost),
                    )
                    for idx, inp in enumerate(inputs)
                ],
            )
