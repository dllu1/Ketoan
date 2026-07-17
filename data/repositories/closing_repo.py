"""Book-closing repository: which fiscal years are closed (chốt sổ)."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from data.database import get_connection


class ClosingRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def closed_years(self) -> set[int]:
        rows = self._conn.execute("SELECT fiscal_year FROM book_closing").fetchall()
        return {int(r["fiscal_year"]) for r in rows}

    def is_closed(self, year: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM book_closing WHERE fiscal_year = ?", (year,)
        ).fetchone()
        return row is not None

    def close(self, year: int, *, auto: bool = False, when: datetime | None = None) -> None:
        when = when or datetime.now()
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO book_closing (fiscal_year, closed_at, auto) "
                "VALUES (?,?,?)",
                (year, when.isoformat(), 1 if auto else 0),
            )

    def reopen(self, year: int) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM book_closing WHERE fiscal_year = ?", (year,)
            )
