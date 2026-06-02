"""parse_money / format_money — pure logic, no DB/Qt."""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.money import format_money, parse_money


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1.000.000", Decimal("1000000")),
        ("1,000,000", Decimal("1000000")),
        ("1000000", Decimal("1000000")),
        ("1.000.000,50", Decimal("1000000.50")),
        ("1,000,000.50", Decimal("1000000.50")),
        ("1000,5", Decimal("1000.5")),
        ("1000.5", Decimal("1000.5")),
        ("", Decimal("0")),
        ("  10.000 ₫ ", Decimal("10000")),
        ("-2.500", Decimal("-2500")),
    ],
)
def test_parse_money(text, expected):
    assert parse_money(text) == expected


def test_parse_money_rejects_junk():
    with pytest.raises(ValueError):
        parse_money("abc")


def test_format_money_round_trip():
    assert format_money(parse_money("1.000.000")) == "1,000,000"
