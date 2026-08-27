"""Opening balances (số dư đầu kỳ) entered per fiscal year.

Reports derive the running balance purely from POSTED journal entries, so a
period whose prior year has no postings shows a zero opening. These records let
the accountant declare an opening baseline — at the account level (Nợ/Có) and,
for stock accounts 152/155/156, detailed per item (quantity + value).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from decimal import Decimal

_ZERO = Decimal("0")


@dataclass
class OpeningBalance:
    fiscal_year: int
    account_code: str
    item_code: str = ""          # "" → dòng cấp tài khoản; có giá trị → chi tiết kho
    opening_debit: Decimal = field(default_factory=lambda: _ZERO)
    opening_credit: Decimal = field(default_factory=lambda: _ZERO)
    opening_qty: Decimal = field(default_factory=lambda: _ZERO)
    opening_value: Decimal = field(default_factory=lambda: _ZERO)
    id: int | None = None

    @property
    def is_item_line(self) -> bool:
        return bool(self.item_code.strip())

    @property
    def is_empty(self) -> bool:
        """A row with no account and nothing entered — skipped on save."""
        return not self.account_code.strip() and not any(
            (self.opening_debit, self.opening_credit,
             self.opening_qty, self.opening_value)
        )

    @property
    def net(self) -> Decimal:
        """Số dư đầu kỳ thuần (Nợ − Có). Stock detail lines use value as a debit."""
        if self.is_item_line:
            return self.opening_value
        return self.opening_debit - self.opening_credit

    @property
    def key(self) -> tuple[str, str]:
        """Khóa duy nhất trong một năm tài chính — trùng khóa là dòng trùng."""
        return self.account_code.strip(), self.item_code.strip()

    def normalized(self) -> "OpeningBalance":
        """Bản sao đã cắt khoảng trắng ở mã tài khoản / mã hàng."""
        return replace(
            self,
            account_code=self.account_code.strip(),
            item_code=self.item_code.strip(),
        )


def find_duplicates(rows: Iterable[OpeningBalance]) -> dict[tuple[str, str], list[int]]:
    """Các khóa (mã TK, mã hàng) xuất hiện nhiều lần → vị trí các dòng đó.

    Khóa này chính là ``UNIQUE(fiscal_year, account_code, item_code)`` của bảng
    ``opening_balance``, nên phát hiện ở đây tránh được lỗi SQL khó hiểu khi lưu.
    """
    seen: dict[tuple[str, str], list[int]] = {}
    for index, row in enumerate(rows):
        seen.setdefault(row.key, []).append(index)
    return {key: idx for key, idx in seen.items() if len(idx) > 1}


def merge_duplicates(rows: Iterable[OpeningBalance]) -> list[OpeningBalance]:
    """Gộp các dòng trùng khóa: cộng dồn SL, giá trị và Nợ/Có đầu kỳ.

    Giữ nguyên thứ tự xuất hiện đầu tiên; ``id`` của dòng đầu được giữ lại để
    dòng gộp thay thế đúng bản ghi cũ.
    """
    merged: dict[tuple[str, str], OpeningBalance] = {}
    for row in rows:
        row = row.normalized()
        current = merged.get(row.key)
        if current is None:
            merged[row.key] = row
            continue
        current.opening_debit += row.opening_debit
        current.opening_credit += row.opening_credit
        current.opening_qty += row.opening_qty
        current.opening_value += row.opening_value
    return list(merged.values())
