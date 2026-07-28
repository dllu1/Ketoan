"""Migration 019 — dọn movement nhập kho 155 do bảng giá thành đẩy (GT-TP).

Hai nhánh phải đúng:

* Mã đã có dòng trong bảng kê TP → bản GT-TP là trùng lặp, xóa đi (hết nhân đôi).
* Mã CHỈ có GT-TP → không được xóa mất tồn, phải nhận nuôi sang BK-TP kèm dòng
  bảng kê tương ứng.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

_MIGRATIONS = Path(__file__).resolve().parents[2] / "data" / "migrations"


def _build_pre_cleanup_db(db_file: Path) -> None:
    """Dựng database ở đúng trạng thái trước khi có migration 019."""
    conn = sqlite3.connect(db_file)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        " version INTEGER PRIMARY KEY, applied_at TEXT)"
    )
    for path in sorted(_MIGRATIONS.glob("*.sql")):
        version = int(path.stem.split("_", 1)[0])
        if version >= 19:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    def movement(code, qty, cost, source, name=""):
        conn.execute(
            "INSERT INTO inventory_movement (item_code, item_name, unit,"
            " account_code, move_date, kind, quantity, unit_cost, source_ref,"
            " note, created_at) VALUES (?,?,'Cái','155','2026-01-01','IN',"
            "?,?,?,'','2026-01-01T00:00:00')",
            (code, name, str(qty), str(cost), source),
        )

    # N12: kế toán đã khai ở bảng kê, bảng giá thành đẩy thêm một bản → nhân đôi.
    conn.execute(
        "INSERT INTO product_sheet_line (period_key, line_no, code, name, unit,"
        " in_price, in_qty, in_value) VALUES"
        " ('2026',0,'N12','Ty 25x30','Cái','29661','1260','37372860')"
    )
    movement("N12", 1260, 0, "BK-TP:2026", "Ty 25x30")
    movement("N12", 1260, 29661, "GT-TP:2026", "Ty 25x30")
    # X99: chỉ tồn tại nhờ bảng giá thành — xóa thẳng là bốc hơi tồn kho.
    movement("X99", 500, 10000, "GT-TP:2026", "Hàng mồ côi")
    conn.commit()
    conn.close()


@pytest.fixture
def migrated(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    _build_pre_cleanup_db(db_file)

    monkeypatch.setattr("app.config.DB_PATH", db_file)
    monkeypatch.setattr("data.database.DB_PATH", db_file)
    import data.database as db_mod
    db_mod._conn = None
    db_mod.init_database()          # áp nốt migration 019
    yield db_mod.get_connection()
    db_mod.close_connection()


def _movements(conn, code):
    return conn.execute(
        "SELECT quantity, unit_cost, source_ref FROM inventory_movement"
        " WHERE item_code = ?", (code,)
    ).fetchall()


def test_no_costing_pushed_movements_remain(migrated):
    left = migrated.execute(
        "SELECT COUNT(*) AS n FROM inventory_movement"
        " WHERE source_ref LIKE 'GT-TP:%'"
    ).fetchone()["n"]
    assert left == 0


def test_duplicate_is_removed_so_quantity_is_no_longer_doubled(migrated):
    rows = _movements(migrated, "N12")
    assert len(rows) == 1
    assert Decimal(str(rows[0]["quantity"])) == Decimal("1260")   # không phải 2520
    assert rows[0]["source_ref"] == "BK-TP:2026"


def test_orphan_keeps_its_stock(migrated):
    """Mã chỉ có GT-TP không được biến mất khỏi kho."""
    rows = _movements(migrated, "X99")
    assert len(rows) == 1
    assert Decimal(str(rows[0]["quantity"])) == Decimal("500")
    assert rows[0]["source_ref"] == "BK-TP:2026"


def test_orphan_gets_a_worksheet_row(migrated):
    """…và phải hiện ra ở Bảng kê TP để còn kéo sang bảng giá thành."""
    row = migrated.execute(
        "SELECT in_qty, in_price FROM product_sheet_line WHERE code = 'X99'"
    ).fetchone()
    assert row is not None
    assert Decimal(str(row["in_qty"])) == Decimal("500")
    assert Decimal(str(row["in_price"])) == Decimal("10000")


def test_existing_worksheet_row_is_not_duplicated(migrated):
    """N12 đã có dòng bảng kê — không được chèn thêm dòng thứ hai."""
    count = migrated.execute(
        "SELECT COUNT(*) AS n FROM product_sheet_line WHERE code = 'N12'"
    ).fetchone()["n"]
    assert count == 1


def test_cleanup_is_not_reapplied(migrated):
    """Migration đã ghi vào schema_version nên không chạy lại lần nữa."""
    version = migrated.execute(
        "SELECT MAX(version) AS v FROM schema_version"
    ).fetchone()["v"]
    assert version >= 19
