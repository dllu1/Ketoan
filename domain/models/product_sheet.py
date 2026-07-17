"""Bảng kê Nhập–Xuất–Tồn thành phẩm — kho 155 (finished-goods NXT worksheet).

Derivation rules, copied from the handwritten form notes:

  * Tiền nhập trong kỳ = giá thành tính trong kỳ (pulled from the costing
    sheet); ĐG nhập = TT nhập / SL nhập.
  * ĐG xuất (bình quân gia quyền)
        = (TT tồn đầu kỳ + TT nhập) / (SL tồn đầu kỳ + SL nhập)
    and TT xuất = ĐG xuất × SL xuất. When the period issues *everything*
    (SL xuất = SL đầu + SL nhập) the whole value goes out, so rounding can
    never strand a few đồng on a zero-quantity balance.
  * Tồn cuối kỳ: SL = đầu + nhập − xuất; TT = đầu + nhập − xuất;
    ĐG = TT cuối / SL cuối.
  * Tồn đầu kỳ tháng này = tồn cuối kỳ tháng trước (carry-forward — the
    service's job).

The same negative-closing invariant as the NVL sheet applies: a closing
balance below zero blocks saving.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

_ZERO = Decimal("0")
_ONE = Decimal("1")


def _unit(value: Decimal, qty: Decimal) -> Decimal:
    return (value / qty).quantize(_ONE, ROUND_HALF_UP) if qty else _ZERO


@dataclass
class ProductLine:
    """One finished product row. The user types đầu kỳ (SL·TT), nhập (SL·TT)
    and SL xuất; every ĐG plus TT xuất and tồn cuối kỳ are derived by
    :meth:`recompute` per the form rules above."""

    code: str
    name: str = ""
    unit: str = ""
    opening_price: Decimal = field(default_factory=lambda: _ZERO)
    opening_qty: Decimal = field(default_factory=lambda: _ZERO)
    opening_value: Decimal = field(default_factory=lambda: _ZERO)
    in_price: Decimal = field(default_factory=lambda: _ZERO)
    in_qty: Decimal = field(default_factory=lambda: _ZERO)
    in_value: Decimal = field(default_factory=lambda: _ZERO)
    out_price: Decimal = field(default_factory=lambda: _ZERO)
    out_qty: Decimal = field(default_factory=lambda: _ZERO)
    out_value: Decimal = field(default_factory=lambda: _ZERO)
    # True for rows synced read-only from the inventory ledger (products that
    # already have real document movements, vd: hóa đơn bán hàng xuất 155).
    # Their out costs come from the ledger, so recompute() leaves them alone.
    from_ledger: bool = False

    def recompute(self) -> None:
        """Derive every computed column of a manual row from its raw inputs."""
        if self.from_ledger:
            return
        self.opening_price = _unit(self.opening_value, self.opening_qty)
        self.in_price = _unit(self.in_value, self.in_qty)
        base_qty = self.opening_qty + self.in_qty
        base_value = self.opening_value + self.in_value
        self.out_price = _unit(base_value, base_qty)
        if self.out_qty <= _ZERO:
            self.out_value = _ZERO
        elif self.out_qty == base_qty:
            self.out_value = base_value
        else:
            self.out_value = (self.out_qty * self.out_price).quantize(
                _ONE, ROUND_HALF_UP
            )

    @property
    def closing_qty(self) -> Decimal:
        return self.opening_qty + self.in_qty - self.out_qty

    @property
    def closing_value(self) -> Decimal:
        return self.opening_value + self.in_value - self.out_value

    @property
    def closing_price(self) -> Decimal:
        return _unit(self.closing_value, self.closing_qty)

    @property
    def is_empty(self) -> bool:
        """A row with no code and nothing entered — skipped on save."""
        return not self.code.strip() and not any(
            (
                self.opening_qty, self.opening_value,
                self.in_qty, self.in_value,
                self.out_qty, self.out_value,
            )
        )

    @property
    def is_negative(self) -> bool:
        """Closing quantity or value below zero — not a valid stock balance."""
        return self.closing_qty < _ZERO or self.closing_value < _ZERO


@dataclass
class ProductSheet:
    period_key: str
    lines: list[ProductLine] = field(default_factory=list)

    @property
    def negative_lines(self) -> list[ProductLine]:
        return [line for line in self.lines if line.is_negative]

    @property
    def has_negative_closing(self) -> bool:
        return any(line.is_negative for line in self.lines)

    @property
    def total_closing_value(self) -> Decimal:
        return sum((line.closing_value for line in self.lines), _ZERO)
