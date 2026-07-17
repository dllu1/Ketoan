"""Opening balances (số dư đầu kỳ) entered per fiscal year.

Reports derive the running balance purely from POSTED journal entries, so a
period whose prior year has no postings shows a zero opening. These records let
the accountant declare an opening baseline — at the account level (Nợ/Có) and,
for stock accounts 152/155/156, detailed per item (quantity + value).
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
