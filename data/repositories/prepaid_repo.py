"""Repository cho chi phí trả trước (TK 242) — bảng ``prepaid_expense``."""
from __future__ import annotations

import sqlite3
from decimal import Decimal

from data.database import get_connection
from domain.models.prepaid import PrepaidExpense


def _row_to_prepaid(row: sqlite3.Row) -> PrepaidExpense:
    return PrepaidExpense(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        total_amount=Decimal(str(row["total_amount"])),
        months=int(row["months"]),
        start_year=int(row["start_year"]),
        start_month=int(row["start_month"]),
        expense_account=row["expense_account"],
        asset_account=row["asset_account"],
        note=row["note"],
    )


class PrepaidRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def list_all(self) -> list[PrepaidExpense]:
        rows = self._conn.execute(
            "SELECT * FROM prepaid_expense ORDER BY start_year, start_month, code"
        ).fetchall()
        return [_row_to_prepaid(r) for r in rows]

    def find_by_code(self, code: str) -> PrepaidExpense | None:
        row = self._conn.execute(
            "SELECT * FROM prepaid_expense WHERE code = ?", (code.strip(),)
        ).fetchone()
        return _row_to_prepaid(row) if row else None

    def insert(self, prepaid: PrepaidExpense) -> PrepaidExpense:
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO prepaid_expense (
                    code, name, total_amount, months, start_year, start_month,
                    expense_account, asset_account, note
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                _params(prepaid),
            )
        prepaid.id = cur.lastrowid
        return prepaid

    def update(self, prepaid: PrepaidExpense) -> PrepaidExpense:
        with self._conn:
            self._conn.execute(
                """
                UPDATE prepaid_expense SET
                    code = ?, name = ?, total_amount = ?, months = ?,
                    start_year = ?, start_month = ?, expense_account = ?,
                    asset_account = ?, note = ?
                WHERE id = ?
                """,
                (*_params(prepaid), prepaid.id),
            )
        return prepaid

    def delete(self, prepaid_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM prepaid_expense WHERE id = ?", (prepaid_id,)
            )


def _params(p: PrepaidExpense) -> tuple:
    return (
        p.code.strip(), p.name, str(p.total_amount), int(p.months),
        int(p.start_year), int(p.start_month),
        p.expense_account, p.asset_account, p.note,
    )
