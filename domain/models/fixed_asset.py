"""FixedAsset: tài sản cố định + khấu hao đường thẳng (TK 211/213 · 214)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

# Khấu hao máy móc dùng cho sản xuất là chi phí sản xuất chung nên vào giá
# thành: công ty hạch toán thẳng vào 15403 (cấp con của 154), 627 giữ cho bộ sổ
# TT200. Các TK còn lại (641/642) là chi phí kỳ, không vào giá thành.
PRODUCTION_EXPENSE_ACCOUNTS = ("15403", "627")


@dataclass
class FixedAsset:
    code: str
    name: str
    asset_account: str = "211"      # 211 hữu hình / 213 vô hình
    expense_account: str = "642"    # TK chi phí khấu hao (15403/627/641/642)
    cost: Decimal = field(default_factory=lambda: Decimal("0"))           # nguyên giá
    salvage_value: Decimal = field(default_factory=lambda: Decimal("0"))  # giá trị thu hồi
    useful_life_months: int = 12
    start_date: date = field(default_factory=date.today)
    notes: str = ""
    active: bool = True
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # ----- straight-line depreciation --------------------------------------

    @property
    def feeds_production_cost(self) -> bool:
        """Khấu hao của tài sản này có vào giá thành (chi phí SX chung) không."""
        return self.expense_account in PRODUCTION_EXPENSE_ACCOUNTS

    @property
    def depreciable_base(self) -> Decimal:
        return max(self.cost - self.salvage_value, Decimal("0"))

    @property
    def monthly_depreciation(self) -> Decimal:
        if self.useful_life_months <= 0:
            return Decimal("0")
        return (self.depreciable_base / self.useful_life_months).quantize(Decimal("1"))

    def period_index(self, year: int, month: int) -> int:
        """1-based index of (year, month) within the depreciation schedule.

        Returns 0 when the period is before the asset's start month."""
        return (year - self.start_date.year) * 12 + (month - self.start_date.month) + 1

    def depreciation_for(self, year: int, month: int) -> Decimal:
        """Khấu hao của riêng tháng (year, month); 0 nếu ngoài thời gian KH.

        The final period absorbs the rounding remainder so accumulated
        depreciation lands exactly on ``depreciable_base``."""
        index = self.period_index(year, month)
        if index < 1 or index > self.useful_life_months:
            return Decimal("0")
        if index == self.useful_life_months:
            return self.depreciable_base - self.monthly_depreciation * (self.useful_life_months - 1)
        return self.monthly_depreciation

    def accumulated_through(self, year: int, month: int) -> Decimal:
        """Lũy kế khấu hao tính đến hết tháng (year, month)."""
        index = max(0, min(self.period_index(year, month), self.useful_life_months))
        if index <= 0:
            return Decimal("0")
        if index >= self.useful_life_months:
            return self.depreciable_base
        return self.monthly_depreciation * index

    def book_value_through(self, year: int, month: int) -> Decimal:
        """Giá trị còn lại đến hết tháng (year, month)."""
        return self.cost - self.accumulated_through(year, month)
