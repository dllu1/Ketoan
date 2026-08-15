"""Zero-balance repository: SQLite access cho danh sách TK phải sạch cuối kỳ."""
from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation

from data.database import get_connection
from domain.models.zero_balance import ZeroBalanceRule


def _to_decimal(value: str) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        # Dung sai gõ sai (vd "1.000") → coi như 0: thà báo lệch còn hơn âm thầm
        # bỏ qua một tài khoản đang treo số dư.
        return Decimal("0")


def _row_to_rule(row: sqlite3.Row) -> ZeroBalanceRule:
    return ZeroBalanceRule(
        id=row["id"],
        account_code=row["account_code"],
        include_children=bool(row["include_children"]),
        tolerance=_to_decimal(row["tolerance"]),
        note=row["note"],
        sort_order=row["sort_order"],
        active=bool(row["active"]),
    )


class ZeroBalanceRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def list_all(self, *, active_only: bool = False) -> list[ZeroBalanceRule]:
        sql = "SELECT * FROM zero_balance_account"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY sort_order, account_code"
        return [_row_to_rule(r) for r in self._conn.execute(sql).fetchall()]

    def count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM zero_balance_account"
        ).fetchone()
        return int(row["n"])

    def replace_all(self, rules: list[ZeroBalanceRule]) -> list[ZeroBalanceRule]:
        """Ghi đè toàn bộ danh sách trong một giao dịch (lưới sửa rồi Lưu một lần)."""
        with self._conn:
            self._conn.execute("DELETE FROM zero_balance_account")
            for order, rule in enumerate(rules, start=1):
                rule.sort_order = rule.sort_order or order * 10
                cursor = self._conn.execute(
                    """
                    INSERT INTO zero_balance_account (
                        account_code, include_children, tolerance, note,
                        sort_order, active
                    ) VALUES (?,?,?,?,?,?)
                    """,
                    (
                        rule.account_code, int(rule.include_children),
                        str(rule.tolerance), rule.note, rule.sort_order,
                        int(rule.active),
                    ),
                )
                rule.id = cursor.lastrowid
        return rules

    def delete_all(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM zero_balance_account")
