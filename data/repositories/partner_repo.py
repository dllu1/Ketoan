"""Partner repository: SQLite access."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from data.database import get_connection
from domain.models.partner import Partner, PartnerType


def _row_to_partner(row: sqlite3.Row) -> Partner:
    return Partner(
        id=row["id"],
        code=row["code"],
        name=row["name"],
        type=PartnerType(row["type"]),
        tax_code=row["tax_code"],
        address=row["address"],
        phone=row["phone"],
        email=row["email"],
        contact_person=row["contact_person"],
        bank_account=row["bank_account"],
        bank_name=row["bank_name"],
        notes=row["notes"],
        active=bool(row["active"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class PartnerRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def list_all(self, type_filter: PartnerType | None = None) -> list[Partner]:
        sql = "SELECT * FROM partner WHERE active = 1"
        params: tuple = ()
        if type_filter is not None:
            sql += " AND (type = ? OR type = 'BOTH')"
            params = (type_filter.value,)
        sql += " ORDER BY code"
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_partner(r) for r in rows]

    def search(self, query: str) -> list[Partner]:
        if not query:
            return self.list_all()
        like = f"%{query}%"
        rows = self._conn.execute(
            "SELECT * FROM partner WHERE active = 1 AND "
            "(code LIKE ? OR name LIKE ? OR tax_code LIKE ?) ORDER BY code",
            (like, like, like),
        ).fetchall()
        return [_row_to_partner(r) for r in rows]

    def find_by_code(self, code: str) -> Partner | None:
        row = self._conn.execute(
            "SELECT * FROM partner WHERE code = ?", (code,)
        ).fetchone()
        return _row_to_partner(row) if row else None

    def find_by_tax_code(self, tax_code: str) -> Partner | None:
        """Đối chiếu đối tác theo MST — khóa tự nhiên của HĐĐT nhập từ email."""
        tax_code = (tax_code or "").strip()
        if not tax_code:
            return None
        row = self._conn.execute(
            "SELECT * FROM partner WHERE tax_code = ? AND tax_code != '' "
            "ORDER BY id LIMIT 1",
            (tax_code,),
        ).fetchone()
        return _row_to_partner(row) if row else None

    def insert(self, partner: Partner) -> Partner:
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO partner (
                    code, name, type, tax_code, address, phone, email,
                    contact_person, bank_account, bank_name, notes, active,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    partner.code, partner.name, partner.type.value,
                    partner.tax_code, partner.address, partner.phone,
                    partner.email, partner.contact_person,
                    partner.bank_account, partner.bank_name, partner.notes,
                    int(partner.active),
                    partner.created_at.isoformat(),
                    partner.updated_at.isoformat(),
                ),
            )
            partner.id = cursor.lastrowid
        return partner

    def update(self, partner: Partner) -> Partner:
        with self._conn:
            self._conn.execute(
                """
                UPDATE partner SET
                    code = ?, name = ?, type = ?, tax_code = ?, address = ?,
                    phone = ?, email = ?, contact_person = ?, bank_account = ?,
                    bank_name = ?, notes = ?, active = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    partner.code, partner.name, partner.type.value,
                    partner.tax_code, partner.address, partner.phone,
                    partner.email, partner.contact_person,
                    partner.bank_account, partner.bank_name, partner.notes,
                    int(partner.active),
                    partner.updated_at.isoformat(),
                    partner.id,
                ),
            )
        return partner

    def set_active(self, partner_id: int, active: bool) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE partner SET active = ?, updated_at = ? WHERE id = ?",
                (int(active), datetime.now().isoformat(), partner_id),
            )
