"""TaxService: thuế GTGT from posted invoices + thuế TNDN from the period result.

VAT is summarised from POSTED invoices only (a draft is a saved document not yet
declared). CIT applies the configurable revenue-banded rate from the plan
(15% / 17% / 20%) to the period's pre-tax accounting profit.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from data.repositories.invoice_repo import InvoiceRepository
from domain.models.invoice import Invoice, InvoiceKind, InvoiceStatus
from domain.models.report import ReportPeriod
from domain.models.tax import (
    CitBracket,
    CitReport,
    VatInvoiceRow,
    VatRateGroup,
    VatReport,
)
from domain.services.report_service import ReportService

_ZERO = Decimal("0")
_B = Decimal("1000000000")   # 1 tỷ VND

# Biểu thuế TNDN theo doanh thu năm (kế hoạch §4): ngưỡng tính theo cận trên.
CIT_BRACKETS: list[CitBracket] = [
    CitBracket(threshold=15 * _B, rate=Decimal("0.15")),
    CitBracket(threshold=50 * _B, rate=Decimal("0.17")),
    CitBracket(threshold=None, rate=Decimal("0.20")),
]


class TaxService:
    def __init__(
        self,
        invoice_repo: InvoiceRepository,
        report_service: ReportService,
    ) -> None:
        self._invoices = invoice_repo
        self._reports = report_service

    # ----- Thuế GTGT --------------------------------------------------------

    def vat_report(self, period: ReportPeriod) -> VatReport:
        report = VatReport(period=period)
        report.output_rows, report.output_groups = self._vat_side(
            period, InvoiceKind.SALE
        )
        report.input_rows, report.input_groups = self._vat_side(
            period, InvoiceKind.PURCHASE
        )
        return report

    def _vat_side(
        self, period: ReportPeriod, kind: InvoiceKind
    ) -> tuple[list[VatInvoiceRow], list[VatRateGroup]]:
        rows: list[VatInvoiceRow] = []
        groups: dict[Decimal, VatRateGroup] = {}
        for inv in self._posted_invoices(period, kind):
            rows.append(
                VatInvoiceRow(
                    invoice_date=inv.invoice_date,
                    invoice_no=inv.invoice_no or inv.ref,
                    serial=inv.serial,
                    partner_name=inv.partner_name or inv.partner_code,
                    partner_tax_code=inv.partner_tax_code,
                    taxable=inv.subtotal,
                    vat=inv.vat_total,
                )
            )
            for line in inv.lines:
                group = groups.setdefault(line.vat_rate, VatRateGroup(rate=line.vat_rate))
                group.taxable += line.amount
                group.vat += line.vat_amount
        rows.sort(key=lambda r: (r.invoice_date, r.invoice_no))
        ordered_groups = [groups[rate] for rate in sorted(groups)]
        return rows, ordered_groups

    def _posted_invoices(
        self, period: ReportPeriod, kind: InvoiceKind
    ) -> list[Invoice]:
        return [
            inv for inv in self._invoices.list_all(kind)
            if inv.status is InvoiceStatus.POSTED
            and period.start <= inv.invoice_date <= period.end
        ]

    # ----- Thuế TNDN --------------------------------------------------------

    def cit_report(self, period: ReportPeriod) -> CitReport:
        # TNDN là thuế theo năm: doanh thu, bậc thuế và lợi nhuận đều tính trên
        # cả năm tài chính của kỳ, bất kể khoảng ngày người dùng chọn. Nếu chọn
        # một phần năm thì bậc thuế theo doanh thu năm mới đúng (không chọn hụt).
        year = period.end.year
        annual = ReportPeriod(start=date(year, 1, 1), end=date(year, 12, 31))
        income = self._reports.income_statement(annual)
        revenue = income.total_revenue
        return CitReport(
            period=annual,
            revenue=revenue,
            profit_before_tax=income.profit_before_tax,
            rate=self.cit_rate(revenue),
        )

    @staticmethod
    def cit_rate(annual_revenue: Decimal) -> Decimal:
        """Pick the CIT rate for a given annual revenue from :data:`CIT_BRACKETS`."""
        for bracket in CIT_BRACKETS:
            if bracket.threshold is None or annual_revenue < bracket.threshold:
                return bracket.rate
        return CIT_BRACKETS[-1].rate
