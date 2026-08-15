"""Global active accounting period (kỳ kế toán).

A single in-memory selection that ledger screens filter against, so the
"KỲ KẾ TOÁN" control in the top bar actually narrows what the user sees.
Ba mức: cả năm, theo quý, theo tháng. ``month is None and quarter is None``
means the whole year (Cả năm) — the default, so nothing is hidden until the
user deliberately picks a narrower period.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from enum import Enum


class PeriodScope(str, Enum):
    """Độ rộng của một kỳ — dùng cho bộ chọn "kết chuyển theo tháng/quý/năm"."""

    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"

    @property
    def label(self) -> str:
        return _SCOPE_LABELS[self]


_SCOPE_LABELS = {
    PeriodScope.MONTH: "Theo tháng",
    PeriodScope.QUARTER: "Theo quý",
    PeriodScope.YEAR: "Theo năm",
}


def quarter_of(month: int) -> int:
    """Quý chứa tháng này: 1..3 → 1, 4..6 → 2, …"""
    return (month - 1) // 3 + 1


@dataclass(frozen=True)
class Period:
    year: int
    month: int | None = None    # None = không lọc theo tháng
    quarter: int | None = None  # None = không lọc theo quý

    def __post_init__(self) -> None:
        # Tháng hẹp hơn quý — khai cả hai thì tháng thắng, để `scope` chỉ có
        # một câu trả lời và date_from/date_to không mâu thuẫn nhau.
        if self.month is not None and self.quarter is not None:
            object.__setattr__(self, "quarter", None)

    # ----- dựng theo từng mức ---------------------------------------------

    @classmethod
    def of_year(cls, year: int) -> "Period":
        return cls(year=year)

    @classmethod
    def of_quarter(cls, year: int, quarter: int) -> "Period":
        return cls(year=year, quarter=quarter)

    @classmethod
    def of_month(cls, year: int, month: int) -> "Period":
        return cls(year=year, month=month)

    # ----- mức của kỳ -------------------------------------------------------

    @property
    def scope(self) -> PeriodScope:
        if self.month is not None:
            return PeriodScope.MONTH
        if self.quarter is not None:
            return PeriodScope.QUARTER
        return PeriodScope.YEAR

    @property
    def months(self) -> list[int]:
        """Các tháng thuộc kỳ — cả năm là 1..12, quý là ba tháng của quý."""
        if self.month is not None:
            return [self.month]
        if self.quarter is not None:
            first = (self.quarter - 1) * 3 + 1
            return list(range(first, first + 3))
        return list(range(1, 13))

    @property
    def anchor_month(self) -> int:
        """Tháng cuối kỳ — mốc lũy kế cho những chỗ chỉ nhận được một tháng."""
        return self.months[-1]

    def with_scope(self, scope: PeriodScope) -> "Period":
        """Cùng năm, cùng mốc tháng, nhưng nới rộng / thu hẹp về đúng mức."""
        if scope is PeriodScope.YEAR:
            return Period(year=self.year)
        if scope is PeriodScope.QUARTER:
            return Period(year=self.year, quarter=quarter_of(self.anchor_month))
        return Period(year=self.year, month=self.anchor_month)

    # ----- lọc / mốc thời gian ---------------------------------------------

    def matches(self, d: date) -> bool:
        if d.year != self.year:
            return False
        if self.month is not None:
            return d.month == self.month
        if self.quarter is not None:
            return quarter_of(d.month) == self.quarter
        return True

    @property
    def key(self) -> str:
        """Worksheet/database period key: '2026', '2026-06' hoặc '2026-Q2'."""
        if self.month is not None:
            return f"{self.year}-{self.month:02d}"
        if self.quarter is not None:
            return f"{self.year}-Q{self.quarter}"
        return str(self.year)

    @property
    def date_from(self) -> date:
        """Ngày đầu kỳ — 01/01 khi chọn cả năm."""
        return date(self.year, self.months[0], 1)

    @property
    def date_to(self) -> date:
        """Ngày cuối kỳ — 31/12 khi chọn cả năm."""
        last = self.anchor_month
        return date(self.year, last, calendar.monthrange(self.year, last)[1])

    # ----- nhãn -------------------------------------------------------------

    @property
    def label(self) -> str:
        if self.month is not None:
            return f"Tháng {self.month:02d}/{self.year}"
        if self.quarter is not None:
            return f"Quý {self.quarter}/{self.year}"
        return f"Cả năm {self.year}"

    @property
    def short_label(self) -> str:
        if self.month is not None:
            return f"{self.month:02d} / {self.year}"
        if self.quarter is not None:
            return f"QUÝ {self.quarter} / {self.year}"
        return f"NĂM {self.year}"

    @property
    def ledger_label(self) -> str:
        if self.month is not None:
            return f"Số cái: kỳ {self.month:02d}/{self.year}"
        if self.quarter is not None:
            return (f"Số cái: quý {self.quarter}/{self.year} "
                    f"({self.date_from:%d.%m} → {self.date_to:%d.%m})")
        return f"Số cái: 01.01.{self.year} → 31.12.{self.year}"


_active: Period = Period(year=date.today().year, month=None)


def active_period() -> Period:
    return _active


def set_active_period(period: Period) -> None:
    global _active
    _active = period
