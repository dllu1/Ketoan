"""TaxScreen: Báo cáo thuế — GTGT (VAT) & TNDN (CIT) view + export (Phase 4)."""
from __future__ import annotations

from data.repositories.account_repo import AccountRepository
from data.repositories.invoice_repo import InvoiceRepository
from data.repositories.journal_repo import JournalRepository
from domain.models.report import ReportPeriod
from domain.services.company_service import CompanyService
from domain.services.report_service import ReportService
from domain.services.tax_service import TaxService
from reports import report_tables as rt
from reports.report_tables import ReportDocument
from ui.screens.report_view import ReportViewScreen


class TaxScreen(ReportViewScreen):
    TITLE = "Báo cáo thuế"
    DEFAULT = "vat"
    OPTIONS = [
        ("vat", "Thuế GTGT"),
        ("vat_declaration", "Tờ khai 01/GTGT"),
        ("cit", "Thuế TNDN"),
    ]

    def _new_services(self) -> None:
        reports = ReportService(JournalRepository(), AccountRepository())
        self._tax = TaxService(InvoiceRepository(), reports)
        self._company = CompanyService()

    def _dispatch(self, key: str, period: ReportPeriod) -> ReportDocument:
        if key == "cit":
            return rt.build_cit_report(self._tax.cit_report(period))
        if key == "vat_declaration":
            return rt.build_vat_declaration(
                self._tax.vat_report(period), self._company.load()
            )
        return rt.build_vat_report(self._tax.vat_report(period))
