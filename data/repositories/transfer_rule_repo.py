"""Transfer-rule repository: SQLite access for the kết chuyển configuration."""
from __future__ import annotations

import sqlite3

from data.database import get_connection
from domain.models.transfer_rule import TransferDirection, TransferRule


def _row_to_rule(row: sqlite3.Row) -> TransferRule:
    return TransferRule(
        id=row["id"],
        group_ref=row["group_ref"],
        label=row["label"],
        source_account=row["source_account"],
        target_account=row["target_account"],
        direction=_direction(row["direction"]),
        include_children=bool(row["include_children"]),
        sort_order=row["sort_order"],
        active=bool(row["active"]),
    )


def _direction(value: str) -> TransferDirection:
    try:
        return TransferDirection(value)
    except ValueError:
        # Cấu hình cũ / gõ tay sai: coi như kết chuyển doanh thu để không vỡ màn
        # hình — người dùng chỉnh lại được ngay trong bảng quy tắc.
        return TransferDirection.DEBIT_SOURCE


class TransferRuleRepository:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    def list_all(self, *, active_only: bool = False) -> list[TransferRule]:
        sql = "SELECT * FROM transfer_rule"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY sort_order, source_account"
        return [_row_to_rule(r) for r in self._conn.execute(sql).fetchall()]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM transfer_rule").fetchone()
        return int(row["n"])

    def insert(self, rule: TransferRule) -> TransferRule:
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO transfer_rule (
                    group_ref, label, source_account, target_account, direction,
                    include_children, sort_order, active
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    rule.group_ref, rule.label, rule.source_account,
                    rule.target_account, rule.direction.value,
                    int(rule.include_children), rule.sort_order, int(rule.active),
                ),
            )
            rule.id = cursor.lastrowid
        return rule

    def replace_all(self, rules: list[TransferRule]) -> list[TransferRule]:
        """Ghi đè toàn bộ bảng quy tắc trong một giao dịch.

        Màn hình Kết chuyển sửa cả lưới rồi bấm Lưu một lần, nên thay trọn bộ
        đơn giản và an toàn hơn là dò từng dòng thêm/sửa/xóa.
        """
        with self._conn:
            self._conn.execute("DELETE FROM transfer_rule")
            for order, rule in enumerate(rules, start=1):
                rule.sort_order = rule.sort_order or order * 10
                cursor = self._conn.execute(
                    """
                    INSERT INTO transfer_rule (
                        group_ref, label, source_account, target_account,
                        direction, include_children, sort_order, active
                    ) VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (
                        rule.group_ref, rule.label, rule.source_account,
                        rule.target_account, rule.direction.value,
                        int(rule.include_children), rule.sort_order,
                        int(rule.active),
                    ),
                )
                rule.id = cursor.lastrowid
        return rules

    def delete_all(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM transfer_rule")
