"""Journal repository: SQLite access for journal entries + their lines."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

from data.database import get_connection
from domain.models.journal import EntryStatus, JournalEntry, JournalLine


def _row_to_entry(row: sqlite3.Row) -> JournalEntry:
    return JournalEntry(
        id=row["id"],
        ref=row["ref"],
        entry_date=date.fromisoformat(str(row["entry_date"])),
        description=row["description"],
        status=EntryStatus(row["status"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _row_to_line(row: sqlite3.Row) -> JournalLine:
    return JournalLine(
        id=row["id"],
        entry_id=row["entry_id"],
        line_no=row["line_no"],
        account_code=row["account_code"],
        account_name=row["account_name"],
        description=row["description"],
        debit=Decimal(str(row["debit"])),
        credit=Decimal(str(row["credit"])),
    )


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class JournalRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def list_all(self) -> list[JournalEntry]:
        rows = self._conn.execute(
            "SELECT * FROM journal_entry ORDER BY entry_date DESC, id DESC"
        ).fetchall()
        return [self._hydrate(_row_to_entry(r)) for r in rows]

    def search(self, query: str) -> list[JournalEntry]:
        if not query:
            return self.list_all()
        like = f"%{query}%"
        rows = self._conn.execute(
            "SELECT * FROM journal_entry WHERE ref LIKE ? OR description LIKE ? "
            "ORDER BY entry_date DESC, id DESC",
            (like, like),
        ).fetchall()
        return [self._hydrate(_row_to_entry(r)) for r in rows]

    def list_lines(self, entry_id: int) -> list[JournalLine]:
        rows = self._conn.execute(
            "SELECT * FROM journal_line WHERE entry_id = ? ORDER BY line_no",
            (entry_id,),
        ).fetchall()
        return [_row_to_line(r) for r in rows]

    def find_by_ref(self, ref: str) -> JournalEntry | None:
        row = self._conn.execute(
            "SELECT * FROM journal_entry WHERE ref = ?", (ref,)
        ).fetchone()
        return self._hydrate(_row_to_entry(row)) if row else None

    def insert(self, entry: JournalEntry) -> JournalEntry:
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO journal_entry (
                    ref, entry_date, description, status, created_at, updated_at
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    entry.ref, entry.entry_date.isoformat(), entry.description,
                    entry.status.value,
                    entry.created_at.isoformat(),
                    entry.updated_at.isoformat(),
                ),
            )
            entry.id = cursor.lastrowid
            self._insert_lines(entry)
        return entry

    def update(self, entry: JournalEntry) -> JournalEntry:
        with self._conn:
            self._conn.execute(
                """
                UPDATE journal_entry SET
                    ref = ?, entry_date = ?, description = ?, status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    entry.ref, entry.entry_date.isoformat(), entry.description,
                    entry.status.value,
                    entry.updated_at.isoformat(),
                    entry.id,
                ),
            )
            self._conn.execute(
                "DELETE FROM journal_line WHERE entry_id = ?", (entry.id,)
            )
            self._insert_lines(entry)
        return entry

    def delete(self, entry_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM journal_entry WHERE id = ?", (entry_id,)
            )

    # ----- helpers ----------------------------------------------------------

    def _hydrate(self, entry: JournalEntry) -> JournalEntry:
        entry.lines = self.list_lines(entry.id)
        return entry

    def _insert_lines(self, entry: JournalEntry) -> None:
        for index, line in enumerate(entry.lines):
            line.entry_id = entry.id
            line.line_no = index
            self._conn.execute(
                """
                INSERT INTO journal_line (
                    entry_id, line_no, account_code, account_name,
                    description, debit, credit
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    entry.id, index, line.account_code, line.account_name,
                    line.description, str(line.debit), str(line.credit),
                ),
            )
