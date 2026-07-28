"""Repository for the raw-material NXT worksheet (material_sheet_line table).

A worksheet is stored as the full set of rows for one period_key; saving
replaces that set wholesale (delete + re-insert), mirroring how the worksheet
is edited as a single document.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

from data.database import get_connection
from domain.models.material_sheet import MaterialLine


def _row_to_line(row: sqlite3.Row) -> MaterialLine:
    return MaterialLine(
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


class MaterialSheetRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def list_for_period(self, period_key: str) -> list[MaterialLine]:
        rows = self._conn.execute(
            "SELECT * FROM material_sheet_line WHERE period_key = ? "
            "ORDER BY line_no, id",
            (period_key,),
        ).fetchall()
        return [_row_to_line(r) for r in rows]

    def list_distinct_materials(self) -> list[tuple[str, str, str]]:
        """(mã, tên, ĐVT) duy nhất theo mã trên mọi kỳ của sổ kho NVL.

        Dùng để đồng bộ NVL đã khai trong kho hàng sang Danh mục vật tư. Khi một
        mã xuất hiện ở nhiều kỳ với tên/ĐVT khác nhau, bản của **kỳ mới nhất**
        được giữ (ORDER BY period_key tăng dần → ghi đè dần trong dict).
        """
        rows = self._conn.execute(
            "SELECT code, name, unit FROM material_sheet_line "
            "WHERE TRIM(code) <> '' ORDER BY period_key, line_no, id"
        ).fetchall()
        latest: dict[str, tuple[str, str]] = {}
        for r in rows:
            latest[r["code"].strip()] = (r["name"], r["unit"])
        return [(code, name, unit) for code, (name, unit) in sorted(latest.items())]

    def replace(self, period_key: str, lines: list[MaterialLine]) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM material_sheet_line WHERE period_key = ?", (period_key,)
            )
            self._conn.executemany(
                """
                INSERT INTO material_sheet_line (
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
