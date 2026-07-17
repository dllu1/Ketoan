"""JournalEntry / JournalLine: atomic unit of the General Journal (Nợ/Có)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class EntryStatus(str, Enum):
    DRAFT = "DRAFT"      # Nháp — chưa cân đối cũng được lưu
    POSTED = "POSTED"    # Đã ghi sổ — bắt buộc Nợ = Có


@dataclass
class JournalLine:
    account_code: str
    account_name: str = ""
    description: str = ""
    debit: Decimal = field(default_factory=lambda: Decimal("0"))
    credit: Decimal = field(default_factory=lambda: Decimal("0"))
    # Đối tượng công nợ (mã khách hàng / nhà cung cấp) cho dòng này — dùng cho
    # các TK theo dõi chi tiết như 131 / 331. Rỗng nếu không gắn đối tượng.
    partner_code: str = ""
    line_no: int = 0
    id: int | None = None
    entry_id: int | None = None


@dataclass
class JournalEntry:
    ref: str
    entry_date: date = field(default_factory=date.today)
    description: str = ""
    status: EntryStatus = EntryStatus.POSTED
    lines: list[JournalLine] = field(default_factory=list)
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def total_debit(self) -> Decimal:
        return sum((line.debit for line in self.lines), Decimal("0"))

    @property
    def total_credit(self) -> Decimal:
        return sum((line.credit for line in self.lines), Decimal("0"))

    @property
    def is_balanced(self) -> bool:
        return self.total_debit == self.total_credit and self.total_debit > 0
