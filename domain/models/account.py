"""Account: a chart-of-accounts entry (configurable per circular)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AccountKind(str, Enum):
    """Phân loại tài khoản (phục vụ báo cáo sau này)."""
    ASSET = "ASSET"            # Tài sản
    LIABILITY = "LIABILITY"    # Nợ phải trả
    EQUITY = "EQUITY"          # Vốn chủ sở hữu
    REVENUE = "REVENUE"        # Doanh thu
    EXPENSE = "EXPENSE"        # Chi phí
    OTHER = "OTHER"            # Khác / ngoài bảng


@dataclass
class Account:
    code: str
    name: str
    kind: str = ""
    circular: str = ""
    active: bool = True
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def display_label(self) -> str:
        return f"{self.code} — {self.name}"
