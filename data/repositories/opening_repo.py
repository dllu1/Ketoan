"""Repository for opening balances (số dư đầu kỳ), keyed by fiscal year.

``replace_for_year`` rewrites the whole year's rows wholesale (idempotent),
mirroring :class:`CostingRepository.replace`.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

from data.database import get_connection
from domain.models.opening import OpeningBalance


def _row_to_opening(row: sqlite3.Row) -> OpeningBalance:
    return OpeningBalance(
        id=row["id"],
        fiscal_year=int(row["fiscal_year"]),
        account_code=row["account_code"],
        item_code=row["item_code"],
        opening_debit=Decimal(str(row["opening_debit"])),
        opening_credit=Decimal(str(row["opening_credit"])),
        opening_qty=Decimal(str(row["opening_qty"])),
        opening_value=Decimal(str(row["opening_value"])),
    )


class OpeningBalanceRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def list_for_year(self, year: int) -> list[OpeningBalance]:
        rows = self._conn.execute(
            "SELECT * FROM opening_balance WHERE fiscal_year = ? "
            "ORDER BY account_code, item_code",
            (year,),
        ).fetchall()
        return [_row_to_opening(r) for r in rows]

    def list_all(self) -> list[OpeningBalance]:
        rows = self._conn.execute(
            "SELECT * FROM opening_balance ORDER BY fiscal_year, account_code, item_code"
        ).fetchall()
        return [_row_to_opening(r) for r in rows]

    def replace_for_year(self, year: int, rows: list[OpeningBalance]) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM opening_balance WHERE fiscal_year = ?", (year,)
            )
            self._conn.executemany(
                "INSERT INTO opening_balance (fiscal_year, account_code, item_code, "
                "opening_debit, opening_credit, opening_qty, opening_value) "
                "VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        year, r.account_code, r.item_code,
                        str(r.opening_debit), str(r.opening_credit),
                        str(r.opening_qty), str(r.opening_value),
                    )
                    for r in rows
                ],
            )
