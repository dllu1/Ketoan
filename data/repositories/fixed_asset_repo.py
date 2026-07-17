"""Fixed asset repository: SQLite access."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

from data.database import get_connection
from domain.models.fixed_asset import FixedAsset


def _row_to_asset(row: sqlite3.Row) -> FixedAsset:
    return FixedAsset(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        asset_account=row["asset_account"],
        expense_account=row["expense_account"],
        cost=Decimal(str(row["cost"])),
        salvage_value=Decimal(str(row["salvage_value"])),
        useful_life_months=row["useful_life_months"],
        start_date=date.fromisoformat(str(row["start_date"])),
        notes=row["notes"],
        active=bool(row["active"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class FixedAssetRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def list_all(self) -> list[FixedAsset]:
        rows = self._conn.execute(
            "SELECT * FROM fixed_asset WHERE active = 1 ORDER BY code"
        ).fetchall()
        return [_row_to_asset(r) for r in rows]

    def search(self, query: str) -> list[FixedAsset]:
        if not query:
            return self.list_all()
        like = f"%{query}%"
        rows = self._conn.execute(
            "SELECT * FROM fixed_asset WHERE active = 1 AND "
            "(code LIKE ? OR name LIKE ?) ORDER BY code",
            (like, like),
        ).fetchall()
        return [_row_to_asset(r) for r in rows]

    def find_by_code(self, code: str) -> FixedAsset | None:
        row = self._conn.execute(
            "SELECT * FROM fixed_asset WHERE code = ?", (code,)
        ).fetchone()
        return _row_to_asset(row) if row else None

    def insert(self, asset: FixedAsset) -> FixedAsset:
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO fixed_asset (
                    code, name, asset_account, expense_account, cost,
                    salvage_value, useful_life_months, start_date, notes,
                    active, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    asset.code, asset.name, asset.asset_account,
                    asset.expense_account, str(asset.cost),
                    str(asset.salvage_value), asset.useful_life_months,
                    asset.start_date.isoformat(), asset.notes,
                    int(asset.active), asset.created_at.isoformat(),
                    asset.updated_at.isoformat(),
                ),
            )
            asset.id = cursor.lastrowid
        return asset

    def update(self, asset: FixedAsset) -> FixedAsset:
        with self._conn:
            self._conn.execute(
                """
                UPDATE fixed_asset SET
                    code = ?, name = ?, asset_account = ?, expense_account = ?,
                    cost = ?, salvage_value = ?, useful_life_months = ?,
                    start_date = ?, notes = ?, active = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    asset.code, asset.name, asset.asset_account,
                    asset.expense_account, str(asset.cost),
                    str(asset.salvage_value), asset.useful_life_months,
                    asset.start_date.isoformat(), asset.notes,
                    int(asset.active), asset.updated_at.isoformat(), asset.id,
                ),
            )
        return asset

    def set_active(self, asset_id: int, active: bool) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE fixed_asset SET active = ?, updated_at = ? WHERE id = ?",
                (int(active), datetime.now().isoformat(), asset_id),
            )
