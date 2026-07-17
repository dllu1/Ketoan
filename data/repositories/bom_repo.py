"""Repository for định mức (bill of materials), keyed by finished product.

``replace_for_product`` rewrites a product's lines wholesale (idempotent),
mirroring :class:`CostingRepository.replace`.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

from data.database import get_connection
from domain.models.bom import BomLine


def _row_to_line(row: sqlite3.Row) -> BomLine:
    return BomLine(
        id=row["id"],
        product_code=row["product_code"],
        material_code=row["material_code"],
        quantity_per=Decimal(str(row["quantity_per"])),
        note=row["note"],
    )


class BomRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def list_for_product(self, product_code: str) -> list[BomLine]:
        rows = self._conn.execute(
            "SELECT * FROM bom_line WHERE product_code = ? ORDER BY material_code, id",
            (product_code,),
        ).fetchall()
        return [_row_to_line(r) for r in rows]

    def list_products(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT product_code FROM bom_line ORDER BY product_code"
        ).fetchall()
        return [r["product_code"] for r in rows]

    def replace_for_product(self, product_code: str, lines: list[BomLine]) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM bom_line WHERE product_code = ?", (product_code,)
            )
            self._conn.executemany(
                "INSERT INTO bom_line (product_code, material_code, quantity_per, note) "
                "VALUES (?,?,?,?)",
                [
                    (product_code, ln.material_code, str(ln.quantity_per), ln.note)
                    for ln in lines
                ],
            )
