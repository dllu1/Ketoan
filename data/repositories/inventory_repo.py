"""Inventory movement repository: SQLite access for the NXT ledger."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

from data.database import get_connection
from domain.models.inventory import InventoryMovement, MovementKind


def _row_to_movement(row: sqlite3.Row) -> InventoryMovement:
    return InventoryMovement(
        id=row["id"],
        item_code=row["item_code"],
        item_name=row["item_name"],
        account_code=row["account_code"],
        move_date=date.fromisoformat(str(row["move_date"])),
        kind=MovementKind(row["kind"]),
        quantity=Decimal(str(row["quantity"])),
        unit_cost=Decimal(str(row["unit_cost"])),
        source_ref=row["source_ref"],
        note=row["note"],
        created_at=_parse_dt(row["created_at"]),
    )


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class InventoryRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def list_all(self) -> list[InventoryMovement]:
        rows = self._conn.execute(
            "SELECT * FROM inventory_movement ORDER BY move_date, id"
        ).fetchall()
        return [_row_to_movement(r) for r in rows]

    def list_for_item(self, item_code: str) -> list[InventoryMovement]:
        rows = self._conn.execute(
            "SELECT * FROM inventory_movement WHERE item_code = ? "
            "ORDER BY move_date, id",
            (item_code,),
        ).fetchall()
        return [_row_to_movement(r) for r in rows]

    def insert(self, movement: InventoryMovement) -> InventoryMovement:
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO inventory_movement (
                    item_code, item_name, account_code, move_date, kind,
                    quantity, unit_cost, source_ref, note, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    movement.item_code, movement.item_name,
                    movement.account_code, movement.move_date.isoformat(),
                    movement.kind.value, str(movement.quantity),
                    str(movement.unit_cost), movement.source_ref,
                    movement.note, movement.created_at.isoformat(),
                ),
            )
            movement.id = cursor.lastrowid
        return movement

    def delete_by_source(self, source_ref: str) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM inventory_movement WHERE source_ref = ?",
                (source_ref,),
            )

    def delete(self, movement_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM inventory_movement WHERE id = ?", (movement_id,)
            )
