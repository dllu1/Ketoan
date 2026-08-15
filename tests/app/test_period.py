"""Kỳ kế toán ba mức: cả năm, theo quý, theo tháng.

Quý là mức mới; các khẳng định về tháng / cả năm ở đây là lưới an toàn để
không làm lệch hành vi cũ khi thêm quý.
"""
from __future__ import annotations

from datetime import date

from app.period import Period, PeriodScope, quarter_of


def test_quarter_of_maps_months_to_quarters():
    assert [quarter_of(m) for m in (1, 3, 4, 6, 7, 9, 10, 12)] == \
        [1, 1, 2, 2, 3, 3, 4, 4]


def test_scope_reports_the_level_of_the_period():
    assert Period.of_month(2026, 6).scope is PeriodScope.MONTH
    assert Period.of_quarter(2026, 2).scope is PeriodScope.QUARTER
    assert Period.of_year(2026).scope is PeriodScope.YEAR


def test_month_wins_when_both_month_and_quarter_are_given():
    """Hai mức mâu thuẫn thì lấy mức hẹp hơn, không để date_from/date_to lệch."""
    period = Period(year=2026, month=5, quarter=4)

    assert period.quarter is None
    assert period.scope is PeriodScope.MONTH
    assert period.date_from == date(2026, 5, 1)


def test_quarter_bounds_cover_the_three_months():
    q2 = Period.of_quarter(2026, 2)

    assert q2.months == [4, 5, 6]
    assert q2.date_from == date(2026, 4, 1)
    assert q2.date_to == date(2026, 6, 30)
    assert q2.anchor_month == 6


def test_quarter_four_ends_on_the_last_day_of_the_year():
    q4 = Period.of_quarter(2026, 4)

    assert q4.date_from == date(2026, 10, 1)
    assert q4.date_to == date(2026, 12, 31)


def test_month_and_year_bounds_are_unchanged():
    assert Period.of_month(2026, 2).date_to == date(2026, 2, 28)
    assert Period.of_month(2024, 2).date_to == date(2024, 2, 29)   # năm nhuận
    assert Period.of_year(2026).date_from == date(2026, 1, 1)
    assert Period.of_year(2026).date_to == date(2026, 12, 31)


def test_matches_filters_by_quarter():
    q2 = Period.of_quarter(2026, 2)

    assert q2.matches(date(2026, 4, 1))
    assert q2.matches(date(2026, 6, 30))
    assert not q2.matches(date(2026, 7, 1))
    assert not q2.matches(date(2025, 5, 5))


def test_period_key_uses_a_q_suffix_for_quarters():
    assert Period.of_year(2026).key == "2026"
    assert Period.of_month(2026, 6).key == "2026-06"
    assert Period.of_quarter(2026, 2).key == "2026-Q2"


def test_labels_name_the_quarter():
    q3 = Period.of_quarter(2026, 3)

    assert q3.label == "Quý 3/2026"
    assert q3.short_label == "QUÝ 3 / 2026"
    assert "quý 3/2026" in q3.ledger_label


def test_with_scope_keeps_the_anchor_month():
    """Đang ở tháng 05 mà đổi sang "theo quý" thì phải ra quý 2, không nhảy đi."""
    may = Period.of_month(2026, 5)

    assert may.with_scope(PeriodScope.QUARTER) == Period.of_quarter(2026, 2)
    assert may.with_scope(PeriodScope.YEAR) == Period.of_year(2026)
    assert may.with_scope(PeriodScope.MONTH) == may


def test_with_scope_narrows_from_year_to_the_end_of_the_period():
    year = Period.of_year(2026)

    assert year.with_scope(PeriodScope.QUARTER) == Period.of_quarter(2026, 4)
    assert year.with_scope(PeriodScope.MONTH) == Period.of_month(2026, 12)
