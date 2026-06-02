"""Shared money parsing/formatting.

A single helper so every numeric input parses identically — important when
users paste amounts from Excel with mixed thousands/decimal separators
(Vietnamese: ``1.000.000,50`` · international: ``1,000,000.50``).
"""
from __future__ import annotations

from decimal import Decimal

_CURRENCY_GLYPHS = "₫đ$  \t"


def parse_money(text: str) -> Decimal:
    """Parse a human-typed amount into a :class:`Decimal`.

    Rules (covers both Vietnamese and international conventions):

    * blank → ``Decimal("0")``;
    * if both ``.`` and ``,`` appear, the *rightmost* one is the decimal
      point and the other is the thousands separator;
    * if only one separator appears, it is treated as a thousands separator
      when its trailing group is exactly 3 digits (``1.000`` / ``1,000`` →
      ``1000``), otherwise as a decimal point (``1000,5`` → ``1000.5``).

    Raises :class:`ValueError` on non-numeric input.
    """
    cleaned = text.strip()
    for glyph in _CURRENCY_GLYPHS:
        cleaned = cleaned.replace(glyph, "")
    if not cleaned:
        return Decimal("0")

    negative = cleaned.startswith("-")
    if negative:
        cleaned = cleaned[1:]

    has_dot = "." in cleaned
    has_comma = "," in cleaned

    if has_dot and has_comma:
        decimal_sep = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        cleaned = cleaned.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif has_dot or has_comma:
        sep = "." if has_dot else ","
        trailing = cleaned.rsplit(sep, 1)[1]
        if len(trailing) == 3 and cleaned.count(sep) >= 1:
            cleaned = cleaned.replace(sep, "")          # thousands grouping
        else:
            cleaned = cleaned.replace(sep, ".")          # decimal point

    if not cleaned or not cleaned.replace(".", "").isdigit():
        raise ValueError(f"Không thể đọc số tiền: {text!r}")

    value = Decimal(cleaned)
    return -value if negative else value


def format_money(value: Decimal) -> str:
    """Format a :class:`Decimal` with thousands grouping (no decimals)."""
    return f"{value:,.0f}"
