"""Account repository: SQLite access for the chart of accounts."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from data.database import get_connection
from domain.models.account import Account


def _row_to_account(row: sqlite3.Row) -> Account:
    return Account(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        kind=row["kind"],
        circular=row["circular"],
        active=bool(row["active"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class AccountRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def list_all(self) -> list[Account]:
        rows = self._conn.execute(
            "SELECT * FROM account WHERE active = 1 ORDER BY code"
        ).fetchall()
        return [_row_to_account(r) for r in rows]

    def search(self, query: str) -> list[Account]:
        if not query:
            return self.list_all()
        like = f"%{query}%"
        rows = self._conn.execute(
            "SELECT * FROM account WHERE active = 1 AND "
            "(code LIKE ? OR name LIKE ?) ORDER BY code",
            (like, like),
        ).fetchall()
        return [_row_to_account(r) for r in rows]

    def find_by_code(self, code: str) -> Account | None:
        row = self._conn.execute(
            "SELECT * FROM account WHERE code = ?", (code,)
        ).fetchone()
        return _row_to_account(row) if row else None

    def insert(self, account: Account) -> Account:
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO account (
                    code, name, kind, circular, active, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    account.code, account.name, account.kind, account.circular,
                    int(account.active),
                    account.created_at.isoformat(),
                    account.updated_at.isoformat(),
                ),
            )
            account.id = cursor.lastrowid
        return account

    def update(self, account: Account) -> Account:
        with self._conn:
            self._conn.execute(
                """
                UPDATE account SET
                    code = ?, name = ?, kind = ?, circular = ?, active = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    account.code, account.name, account.kind, account.circular,
                    int(account.active),
                    account.updated_at.isoformat(),
                    account.id,
                ),
            )
        return account

    def set_active(self, account_id: int, active: bool) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE account SET active = ?, updated_at = ? WHERE id = ?",
                (int(active), datetime.now().isoformat(), account_id),
            )
