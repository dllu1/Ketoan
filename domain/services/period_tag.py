"""Nhãn kỳ dùng trong số chứng từ kết chuyển (dùng chung KC-GV / KC-DT…)."""
from __future__ import annotations

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
