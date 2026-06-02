"""SQLite connection + migration runner."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Lock

from app.config import DB_PATH

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_conn: sqlite3.Connection | None = None
_lock = Lock()


def get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                # No detect_types: TIMESTAMP columns are read back as raw ISO
                # strings and parsed by each repo's _parse_dt (datetime.
                # fromisoformat). The built-in sqlite3 timestamp converter is
                # deprecated (3.12+) and crashes on the 'T' separator that
                # .isoformat() emits.
                _conn = sqlite3.connect(
                    DB_PATH,
                    check_same_thread=False,
                )
                _conn.row_factory = sqlite3.Row
                _conn.execute("PRAGMA foreign_keys = ON")
                _conn.execute("PRAGMA journal_mode = WAL")
    return _conn


def init_database() -> None:
    conn = get_connection()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
    )
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    current = row["v"] or 0

    for migration in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        version = int(migration.stem.split("_", 1)[0])
        if version <= current:
            continue
        with conn:
            conn.executescript(migration.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (version,)
            )


def close_connection() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None
