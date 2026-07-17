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
        partner_code=row["partner_code"],
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
        entries = [_row_to_entry(r) for r in rows]
        # Một truy vấn lấy toàn bộ dòng (tránh N+1: trước đây mỗi bút toán một
        # query). Báo cáo quét cả sổ nên đây là điểm tăng tốc lớn nhất.
        by_id = {e.id: e for e in entries}
        for entry in entries:
            entry.lines = []
        for line_row in self._conn.execute(
            "SELECT * FROM journal_line ORDER BY entry_id, line_no"
        ):
            entry = by_id.get(line_row["entry_id"])
            if entry is not None:
                entry.lines.append(_row_to_line(line_row))
        return entries

    def search(self, query: str) -> list[JournalEntry]:
        if not query:
            return self.list_all()
        like = f"%{query}%"
        rows = self._conn.execute(
            "SELECT * FROM journal_entry WHERE ref LIKE ? OR description LIKE ? "
            "ORDER BY entry_date DESC, id DESC",
            (like, like),
        ).fetchall()
        return self._attach_lines([_row_to_entry(r) for r in rows])

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

    def _attach_lines(self, entries: list[JournalEntry]) -> list[JournalEntry]:
        """Nạp dòng cho nhiều bút toán bằng truy vấn gộp (tránh N+1).

        Chia lô tham số IN(...) để không vượt giới hạn biến của SQLite khi danh
        sách rất dài.
        """
        by_id = {e.id: e for e in entries}
        for entry in entries:
            entry.lines = []
        ids = list(by_id)
        for start in range(0, len(ids), 900):
            chunk = ids[start:start + 900]
            placeholders = ",".join("?" * len(chunk))
            rows = self._conn.execute(
                f"SELECT * FROM journal_line WHERE entry_id IN ({placeholders}) "
                "ORDER BY entry_id, line_no",
                tuple(chunk),
            ).fetchall()
            for line_row in rows:
                by_id[line_row["entry_id"]].lines.append(_row_to_line(line_row))
        return entries

    def _insert_lines(self, entry: JournalEntry) -> None:
        for index, line in enumerate(entry.lines):
            line.entry_id = entry.id
            line.line_no = index
            self._conn.execute(
                """
                INSERT INTO journal_line (
                    entry_id, line_no, account_code, account_name,
                    description, debit, credit, partner_code
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    entry.id, index, line.account_code, line.account_name,
                    line.description, str(line.debit), str(line.credit),
                    line.partner_code,
                ),
            )
