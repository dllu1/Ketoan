"""Item repository: SQLite access."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal

from data.database import get_connection
from domain.models.item import Item, ItemCategory


def _row_to_item(row: sqlite3.Row) -> Item:
    return Item(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        category=ItemCategory(row["category"]),
        unit=row["unit"],
        unit_price=Decimal(str(row["unit_price"])),
        vat_rate=Decimal(str(row["vat_rate"])),
        account_code=row["account_code"],
        notes=row["notes"],
        active=bool(row["active"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class ItemRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def list_all(self, category: ItemCategory | None = None) -> list[Item]:
        sql = "SELECT * FROM item WHERE active = 1"
        params: tuple = ()
        if category is not None:
            sql += " AND category = ?"
            params = (category.value,)
        sql += " ORDER BY code"
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_item(r) for r in rows]

    def search(self, query: str) -> list[Item]:
        if not query:
            return self.list_all()
        like = f"%{query}%"
        rows = self._conn.execute(
            "SELECT * FROM item WHERE active = 1 AND "
            "(code LIKE ? OR name LIKE ?) ORDER BY code",
            (like, like),
        ).fetchall()
        return [_row_to_item(r) for r in rows]

    def find_by_code(self, code: str) -> Item | None:
        row = self._conn.execute(
            "SELECT * FROM item WHERE code = ?", (code,)
        ).fetchone()
        return _row_to_item(row) if row else None

    def insert(self, item: Item) -> Item:
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO item (
                    code, name, category, unit, unit_price, vat_rate,
                    account_code, notes, active, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    item.code, item.name, item.category.value, item.unit,
                    str(item.unit_price), str(item.vat_rate),
                    item.account_code, item.notes, int(item.active),
                    item.created_at.isoformat(),
                    item.updated_at.isoformat(),
                ),
            )
            item.id = cursor.lastrowid
        return item

    def update(self, item: Item) -> Item:
        with self._conn:
            self._conn.execute(
                """
                UPDATE item SET
                    code = ?, name = ?, category = ?, unit = ?,
                    unit_price = ?, vat_rate = ?, account_code = ?,
                    notes = ?, active = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    item.code, item.name, item.category.value, item.unit,
                    str(item.unit_price), str(item.vat_rate),
                    item.account_code, item.notes, int(item.active),
                    item.updated_at.isoformat(),
                    item.id,
                ),
            )
        return item

    def delete(self, item_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM item WHERE id = ?", (item_id,))
