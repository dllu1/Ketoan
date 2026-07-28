"""Chi phí trả trước (TK 242 / 1421 / 1422) và lịch phân bổ theo tháng.

Sổ tay "Nhập liệu" mục I.3.d: khoản chi phí dùng cho nhiều kỳ được treo vào TK
chi phí trả trước rồi **phân bổ dần** ra từng tháng, mỗi tháng ghi
``Nợ TK chi phí / Có 242``.

Chia đều cho ``months`` tháng; phần lẻ do làm tròn dồn vào **tháng cuối** để
tổng phân bổ luôn đúng bằng ``total_amount``, không thừa/thiếu đồng nào.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

_ZERO = Decimal("0")
_ONE = Decimal("1")


@dataclass
class PrepaidExpense:
    code: str
    name: str = ""
    total_amount: Decimal = field(default_factory=lambda: _ZERO)
    months: int = 1
    start_year: int = 0
    start_month: int = 1
    expense_account: str = "642"   # TK chi phí nhận phân bổ hằng tháng
    asset_account: str = "242"     # TK treo chi phí trả trước
    note: str = ""
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)

    # ----- lịch phân bổ ---------------------------------------------------

    @property
    def monthly_amount(self) -> Decimal:
        """Số phân bổ mỗi tháng (mọi tháng trừ tháng cuối)."""
        if self.months <= 0:
            return _ZERO
        return (self.total_amount / Decimal(self.months)).quantize(_ONE)

    def offset_of(self, year: int, month: int) -> int:
        """Tháng thứ mấy trong lịch phân bổ (0 = tháng bắt đầu)."""
        return (year - self.start_year) * 12 + (month - self.start_month)

    def covers(self, year: int, month: int) -> bool:
        return 0 <= self.offset_of(year, month) < self.months

    def amount_for(self, year: int, month: int) -> Decimal:
        """Số phân bổ của một tháng; 0 nếu ngoài lịch.

        Tháng cuối nhận phần còn lại nên tổng cả lịch = ``total_amount``.
        """
        if not self.covers(year, month) or self.total_amount <= _ZERO:
            return _ZERO
        offset = self.offset_of(year, month)
        if offset == self.months - 1:
            return self.total_amount - self.monthly_amount * Decimal(self.months - 1)
        return self.monthly_amount

    def allocated_through(self, year: int, month: int) -> Decimal:
        """Lũy kế đã phân bổ tính đến hết tháng ``year/month``."""
        offset = self.offset_of(year, month)
        if offset < 0 or self.total_amount <= _ZERO:
            return _ZERO
        if offset >= self.months - 1:
            return self.total_amount
        return self.monthly_amount * Decimal(offset + 1)

    def remaining_after(self, year: int, month: int) -> Decimal:
        """Số còn lại chưa phân bổ sau tháng ``year/month``."""
        return self.total_amount - self.allocated_through(year, month)

    @property
    def end_year(self) -> int:
        return self.start_year + (self.start_month - 1 + self.months - 1) // 12

    @property
    def end_month(self) -> int:
        return (self.start_month - 1 + self.months - 1) % 12 + 1

    @property
    def is_empty(self) -> bool:
        return not self.code.strip() and self.total_amount <= _ZERO


@dataclass
class PrepaidScheduleRow:
    """Một dòng lịch phân bổ (dùng cho bảng T01…T12 trên giao diện)."""

    year: int
    month: int
    amount: Decimal = field(default_factory=lambda: _ZERO)
    allocated: Decimal = field(default_factory=lambda: _ZERO)
    remaining: Decimal = field(default_factory=lambda: _ZERO)

    @property
    def label(self) -> str:
        return f"T{self.month:02d}/{self.year}"
