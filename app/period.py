"""Global active accounting period (kỳ kế toán).

A single in-memory selection that ledger screens filter against, so the
"KỲ KẾ TOÁN" control in the top bar actually narrows what the user sees.
``month is None`` means the whole year (Cả năm) — the default, so nothing is
hidden until the user deliberately picks a month.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Period:
    year: int
    month: int | None = None  # None = cả năm

    def matches(self, d: date) -> bool:
        if d.year != self.year:
            return False
        return self.month is None or d.month == self.month

    @property
    def key(self) -> str:
        """Worksheet/database period key: '2026' (cả năm) or '2026-06'."""
        if self.month is None:
            return str(self.year)
        return f"{self.year}-{self.month:02d}"

    @property
    def label(self) -> str:
        if self.month is None:
            return f"Cả năm {self.year}"
        return f"Tháng {self.month:02d}/{self.year}"

    @property
    def short_label(self) -> str:
        if self.month is None:
            return f"NĂM {self.year}"
        return f"{self.month:02d} / {self.year}"

    @property
    def ledger_label(self) -> str:
        if self.month is None:
            return f"Số cái: 01.01.{self.year} → 31.12.{self.year}"
        return f"Số cái: kỳ {self.month:02d}/{self.year}"


_active: Period = Period(year=date.today().year, month=None)


def active_period() -> Period:
    return _active


def set_active_period(period: Period) -> None:
    global _active
    _active = period
