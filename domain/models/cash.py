"""Cash & bank vouchers (phiếu thu / phiếu chi) over accounts 111 / 112.

A voucher is just a focused two-line journal entry; the cash module derives its
movement list from the journal rather than owning a separate table.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

# Tài khoản tiền theo dõi trong module Quỹ & Ngân hàng.
CASH_ACCOUNTS: dict[str, str] = {
    "111": "Tiền mặt",
    "112": "Tiền gửi ngân hàng",
}


class CashKind(str, Enum):
    RECEIPT = "RECEIPT"   # Phiếu thu — tiền vào (Nợ TK tiền)
    PAYMENT = "PAYMENT"   # Phiếu chi — tiền ra (Có TK tiền)


@dataclass
class CashMovement:
    """A derived view row: one journal line that touches a cash account."""
    entry_date: date
    ref: str
    description: str
    cash_account: str
    counter_account: str
    inflow: Decimal = field(default_factory=lambda: Decimal("0"))
    outflow: Decimal = field(default_factory=lambda: Decimal("0"))
    balance: Decimal = field(default_factory=lambda: Decimal("0"))
