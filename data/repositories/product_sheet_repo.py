"""Repository for the finished-goods NXT worksheet (product_sheet_line table).

A worksheet is stored as the full set of rows for one period_key; saving
replaces that set wholesale (delete + re-insert), mirroring how the worksheet
is edited as a single document — same contract as MaterialSheetRepository.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

from data.database import get_connection
from domain.models.product_sheet import ProductLine


def _row_to_line(row: sqlite3.Row) -> ProductLine:
    return ProductLine(
        code=row["code"],
        name=row["name"],
        unit=row["unit"],
        opening_price=Decimal(str(row["opening_price"])),
        opening_qty=Decimal(str(row["opening_qty"])),
        opening_value=Decimal(str(row["opening_value"])),
        in_price=Decimal(str(row["in_price"])),
        in_qty=Decimal(str(row["in_qty"])),
        in_value=Decimal(str(row["in_value"])),
        out_price=Decimal(str(row["out_price"])),
        out_qty=Decimal(str(row["out_qty"])),
        out_value=Decimal(str(row["out_value"])),
    )


class ProductSheetRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def list_for_period(self, period_key: str) -> list[ProductLine]:
        rows = self._conn.execute(
            "SELECT * FROM product_sheet_line WHERE period_key = ? "
            "ORDER BY line_no, id",
            (period_key,),
        ).fetchall()
        return [_row_to_line(r) for r in rows]

    def replace(self, period_key: str, lines: list[ProductLine]) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM product_sheet_line WHERE period_key = ?", (period_key,)
            )
            self._conn.executemany(
                """
                INSERT INTO product_sheet_line (
                    period_key, line_no, code, name, unit,
                    opening_price, opening_qty, opening_value,
                    in_price, in_qty, in_value,
                    out_price, out_qty, out_value
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        period_key, idx, line.code, line.name, line.unit,
                        str(line.opening_price), str(line.opening_qty),
                        str(line.opening_value),
                        str(line.in_price), str(line.in_qty), str(line.in_value),
                        str(line.out_price), str(line.out_qty), str(line.out_value),
                    )
                    for idx, line in enumerate(lines)
                ],
            )
