"""Quy tắc "tài khoản không có số dư cuối kỳ" + kết quả kiểm tra."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

_ZERO = Decimal("0")


@dataclass
class ZeroBalanceRule:
    """Một tài khoản phải hết số dư vào cuối kỳ.

    ``tolerance`` là mức lệch còn chấp nhận (chênh lệch làm tròn khi phân bổ giá
    thành); 0 nghĩa là phải sạch tuyệt đối.
    """

    account_code: str
    include_children: bool = True
    tolerance: Decimal = _ZERO
    note: str = ""
    sort_order: int = 0
    active: bool = True
    id: int | None = None

    def matches(self, code: str) -> bool:
        target = self.account_code.strip()
        if not target:
            return False
        return code.startswith(target) if self.include_children else code == target

    @property
    def specificity(self) -> int:
        """Độ dài mã — mã dài hơn thắng khi một TK khớp nhiều quy tắc."""
        return len(self.account_code.strip())

    def is_violation(self, balance: Decimal) -> bool:
        return abs(balance) > abs(self.tolerance)


@dataclass
class ZeroBalanceIssue:
    """Một tài khoản đáng lẽ phải sạch nhưng vẫn còn số dư."""

    account_code: str
    account_name: str
    balance: Decimal            # net Nợ − Có: >0 dư Nợ, <0 dư Có
    tolerance: Decimal = _ZERO
    note: str = ""

    @property
    def debit_balance(self) -> Decimal:
        return self.balance if self.balance > _ZERO else _ZERO

    @property
    def credit_balance(self) -> Decimal:
        return -self.balance if self.balance < _ZERO else _ZERO

    @property
    def side_label(self) -> str:
        return "Dư Nợ" if self.balance > _ZERO else "Dư Có"


@dataclass
class ZeroBalanceReport:
    """Kết quả một lượt kiểm tra số dư cuối kỳ."""

    as_of: date
    checked_accounts: int = 0
    issues: list[ZeroBalanceIssue] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.issues

    @property
    def total(self) -> Decimal:
        """Tổng giá trị tuyệt đối số dư còn treo — nêu nhanh mức độ lệch."""
        return sum((abs(i.balance) for i in self.issues), _ZERO)
