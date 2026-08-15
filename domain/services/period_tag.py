"""Tiện ích kỳ kế toán dùng chung ở tầng domain.

Gồm nhãn kỳ cho số chứng từ kết chuyển (KC-GV / KC-DT…) và cách quy một kỳ
tháng / quý / cả năm về danh sách tháng.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date


def period_tag(date_from: date, date_to: date) -> str:
    """Cả năm → ``2025``; tháng → ``2025-10``; quý → ``2025-Q4``; khác → dd..-dd.."""
    if (date_from.month, date_from.day) == (1, 1) and \
            (date_to.month, date_to.day) == (12, 31) and \
            date_from.year == date_to.year:
        return str(date_from.year)
    if date_from.year == date_to.year and date_from.month == date_to.month:
        return f"{date_from.year}-{date_from.month:02d}"
    if date_from.year == date_to.year:
        quarter = (date_from.month - 1) // 3 + 1
        if date_from.month == (quarter - 1) * 3 + 1 and date_to.month == quarter * 3:
            return f"{date_from.year}-Q{quarter}"
    return f"{date_from:%d%m%y}-{date_to:%d%m%y}"


def child_period_keys(period_key: str) -> list[str]:
    """Các kỳ con trực tiếp, theo thứ tự thời gian.

    ``'2026'`` → bốn quý; ``'2026-Q2'`` → ba tháng; ``'2026-06'`` → rỗng (đã là
    mức hẹp nhất). Bảng kê của kỳ rộng gộp số liệu từ đây.
    """
    parts = period_key.split("-")
    year = parts[0]
    if len(parts) == 1:
        return [f"{year}-Q{q}" for q in range(1, 5)]
    if parts[1].upper().startswith("Q"):
        first = (int(parts[1][1:]) - 1) * 3 + 1
        return [f"{year}-{m:02d}" for m in range(first, first + 3)]
    return []


def months_in(month: int | Iterable[int] | None) -> tuple[int, ...]:
    """Chuẩn hóa "kỳ" thành dãy tháng: ``None`` = cả năm, số = một tháng,
    dãy số = kỳ nhiều tháng (quý)."""
    if month is None:
        return tuple(range(1, 13))
    if isinstance(month, int):
        return (month,)
    return tuple(month)
