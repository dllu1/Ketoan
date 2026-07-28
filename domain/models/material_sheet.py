"""Bảng kê Nhập–Xuất–Tồn nguyên vật liệu chính (raw-material NXT worksheet).

A manually-entered worksheet (one :class:`MaterialLine` per material) where the
accountant fills đầu kỳ / nhập / xuất and the closing balance (tồn cuối kỳ) is
*derived*: ``closing = opening + in − out`` for both quantity and value.

The accounting invariant the worksheet enforces is that a closing balance can
never go negative — you cannot have issued more than you held. A line whose
closing quantity *or* value is below zero is flagged via
:attr:`MaterialLine.is_negative` so the UI can paint it red and the service can
refuse to save the sheet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

_ZERO = Decimal("0")


@dataclass
class MaterialLine:
    """One material row. ``*_price`` columns are the worksheet's informational
    đơn giá (kept for faithfulness to the paper form); only quantities and
    values drive the closing balance."""

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
    # True for rows synced read-only from the inventory ledger (materials that
    # already have real document movements). Such rows are displayed but never
    # re-pushed to the ledger on save, so they can't double-count mua/bán.
    from_ledger: bool = False
    # Phần xuất do bảng giá thành sinh ra (nguồn GT-NVL): NVL tiêu hao theo định
    # mức. Hiển thị và trừ vào tồn như mọi khoản xuất khác, nhưng KHÔNG lưu vào
    # material_sheet_line và không đẩy lại sổ kho khi lưu — nó đã nằm sẵn trong
    # sổ kho rồi, ghi thêm lần nữa là trừ kho hai lần.
    issued_qty: Decimal = field(default_factory=lambda: _ZERO)
    issued_value: Decimal = field(default_factory=lambda: _ZERO)

    @property
    def total_out_qty(self) -> Decimal:
        """Tổng xuất hiển thị = xuất nhập tay + xuất theo giá thành."""
        return self.out_qty + self.issued_qty

    @property
    def total_out_value(self) -> Decimal:
        return self.out_value + self.issued_value

    @property
    def closing_qty(self) -> Decimal:
        return self.opening_qty + self.in_qty - self.total_out_qty

    @property
    def closing_value(self) -> Decimal:
        return self.opening_value + self.in_value - self.total_out_value

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
class MaterialSheet:
    period_key: str
    lines: list[MaterialLine] = field(default_factory=list)

    @property
    def negative_lines(self) -> list[MaterialLine]:
        return [line for line in self.lines if line.is_negative]

    @property
    def has_negative_closing(self) -> bool:
        return any(line.is_negative for line in self.lines)

    @property
    def total_opening_value(self) -> Decimal:
        return sum((line.opening_value for line in self.lines), _ZERO)

    @property
    def total_in_value(self) -> Decimal:
        return sum((line.in_value for line in self.lines), _ZERO)

    @property
    def total_out_value(self) -> Decimal:
        return sum((line.total_out_value for line in self.lines), _ZERO)

    @property
    def total_closing_value(self) -> Decimal:
        return sum((line.closing_value for line in self.lines), _ZERO)
