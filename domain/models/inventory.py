"""Inventory movements + NXT (Nhập-Xuất-Tồn) for stock accounts 152/153/155/156.

The movement ledger is the single source of truth. Stock value uses the
*weighted-average* method (bình quân gia quyền): every OUT movement is costed at
the running average at the moment it is recorded, and that cost is stored, so the
NXT report is a plain aggregation rather than a re-derivation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

_ZERO = Decimal("0")
_ONE = Decimal("1")


def _unit_price(value: Decimal, qty: Decimal) -> Decimal:
    """Đơn giá = tổng tiền / số lượng, làm tròn về đồng (0 khi SL = 0)."""
    return (value / qty).quantize(_ONE) if qty else _ZERO


class MovementKind(str, Enum):
    OPENING = "OPENING"   # Tồn đầu kỳ
    IN = "IN"             # Nhập kho (mua / nhận)
    OUT = "OUT"           # Xuất kho (bán / sử dụng)

    @property
    def is_inbound(self) -> bool:
        return self is not MovementKind.OUT


@dataclass
class InventoryMovement:
    item_code: str
    move_date: date = field(default_factory=date.today)
    kind: MovementKind = MovementKind.IN
    quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    unit_cost: Decimal = field(default_factory=lambda: Decimal("0"))
    account_code: str = ""        # 152/153/155/156
    item_name: str = ""
    source_ref: str = ""          # chứng từ gốc (vd: số hóa đơn bán hàng)
    note: str = ""
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def value(self) -> Decimal:
        return self.quantity * self.unit_cost

    @property
    def signed_quantity(self) -> Decimal:
        return self.quantity if self.kind.is_inbound else -self.quantity

    @property
    def signed_value(self) -> Decimal:
        return self.value if self.kind.is_inbound else -self.value


@dataclass
class NxtRow:
    """One line of the NXT report (per item)."""
    item_code: str
    item_name: str = ""
    unit: str = ""
    account_code: str = ""
    opening_qty: Decimal = field(default_factory=lambda: Decimal("0"))
    opening_value: Decimal = field(default_factory=lambda: Decimal("0"))
    in_qty: Decimal = field(default_factory=lambda: Decimal("0"))
    in_value: Decimal = field(default_factory=lambda: Decimal("0"))
    out_qty: Decimal = field(default_factory=lambda: Decimal("0"))
    out_value: Decimal = field(default_factory=lambda: Decimal("0"))

    @property
    def closing_qty(self) -> Decimal:
        return self.opening_qty + self.in_qty - self.out_qty

    @property
    def closing_value(self) -> Decimal:
        return self.opening_value + self.in_value - self.out_value

    # Đơn giá của mỗi giai đoạn = TT / SL (làm tròn về đồng). Kho hàng hiển thị
    # đủ ĐG · SL · TT cho tồn đầu kỳ / nhập / xuất / tồn cuối kỳ.
    @property
    def opening_price(self) -> Decimal:
        return _unit_price(self.opening_value, self.opening_qty)

    @property
    def in_price(self) -> Decimal:
        return _unit_price(self.in_value, self.in_qty)

    @property
    def out_price(self) -> Decimal:
        return _unit_price(self.out_value, self.out_qty)

    @property
    def closing_price(self) -> Decimal:
        return _unit_price(self.closing_value, self.closing_qty)
