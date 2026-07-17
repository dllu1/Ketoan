"""Tax report value objects: thuế GTGT (VAT) and thuế TNDN (CIT).

Like :mod:`domain.models.report`, these are derived read-models — never
persisted. VAT figures come from posted invoices; CIT is computed from the
period's accounting result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from domain.models.report import ReportPeriod

_ZERO = Decimal("0")
_DONG = Decimal("1")


# --- Thuế GTGT (Value-Added Tax) ------------------------------------------


@dataclass
class VatInvoiceRow:
    """One invoice on a bảng kê (output or input)."""
    invoice_date: date
    invoice_no: str
    serial: str
    partner_name: str
    partner_tax_code: str
    taxable: Decimal = field(default_factory=lambda: _ZERO)   # giá trị chưa thuế
    vat: Decimal = field(default_factory=lambda: _ZERO)       # tiền thuế GTGT


@dataclass
class VatRateGroup:
    """Subtotal of taxable base + VAT for a single rate (0/5/8/10%)."""
    rate: Decimal
    taxable: Decimal = field(default_factory=lambda: _ZERO)
    vat: Decimal = field(default_factory=lambda: _ZERO)


@dataclass
class VatReport:
    period: ReportPeriod
    output_rows: list[VatInvoiceRow] = field(default_factory=list)
    input_rows: list[VatInvoiceRow] = field(default_factory=list)
    output_groups: list[VatRateGroup] = field(default_factory=list)
    input_groups: list[VatRateGroup] = field(default_factory=list)

    @property
    def output_taxable(self) -> Decimal:
        return sum((r.taxable for r in self.output_rows), _ZERO)

    @property
    def output_vat(self) -> Decimal:
        return sum((r.vat for r in self.output_rows), _ZERO)

    @property
    def input_taxable(self) -> Decimal:
        return sum((r.taxable for r in self.input_rows), _ZERO)

    @property
    def input_vat(self) -> Decimal:
        return sum((r.vat for r in self.input_rows), _ZERO)

    @property
    def vat_payable(self) -> Decimal:
        """Thuế GTGT phải nộp (đầu ra − đầu vào).

        Negative ⇒ thuế còn được khấu trừ chuyển kỳ sau.
        """
        return self.output_vat - self.input_vat


# --- Thuế TNDN (Corporate Income Tax) -------------------------------------


@dataclass(frozen=True)
class CitBracket:
    """A CIT rate that applies up to ``threshold`` of annual revenue."""
    threshold: Decimal | None   # None = the top, open-ended bracket
    rate: Decimal               # decimal fraction, e.g. Decimal("0.15")

    @property
    def label(self) -> str:
        return f"{self.rate * 100:g}%"


@dataclass
class CitReport:
    period: ReportPeriod
    revenue: Decimal
    profit_before_tax: Decimal
    rate: Decimal               # decimal fraction actually applied

    @property
    def rate_label(self) -> str:
        return f"{self.rate * 100:g}%"

    @property
    def taxable_profit(self) -> Decimal:
        """Lãi chịu thuế — a loss yields zero CIT (no negative tax)."""
        return self.profit_before_tax if self.profit_before_tax > 0 else _ZERO

    @property
    def tax_amount(self) -> Decimal:
        return (self.taxable_profit * self.rate).quantize(_DONG)

    @property
    def profit_after_tax(self) -> Decimal:
        return self.profit_before_tax - self.tax_amount
