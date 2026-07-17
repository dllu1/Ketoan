"""ReportsScreen: Báo cáo tài chính — view + Excel/PDF export (Phase 4)."""
from __future__ import annotations

from data.repositories.account_repo import AccountRepository
from data.repositories.journal_repo import JournalRepository
from domain.models.report import ReportPeriod
from domain.services.report_service import ReportService
from reports import report_tables as rt
from reports.report_tables import ReportDocument
from ui.screens.report_view import ReportViewScreen


class ReportsScreen(ReportViewScreen):
    TITLE = "Báo cáo tài chính"
    DEFAULT = "journal"
    OPTIONS = [
        ("journal", "Nhật ký chung"),
        ("ledger", "Sổ cái"),
        ("trial", "Cân đối TK"),
        ("income", "KQ kinh doanh"),
        ("balance", "Cân đối kế toán"),
        ("cashflow", "Lưu chuyển tiền"),
        ("debt_ar", "CN phải thu"),
        ("debt_ap", "CN phải trả"),
    ]

    def _new_services(self) -> None:
        self._service = ReportService(JournalRepository(), AccountRepository())

    def _account_filter_keys(self) -> set[str]:
        return {"ledger"}

    def _dispatch(self, key: str, period: ReportPeriod) -> ReportDocument:
        if key == "ledger":
            code = self._account_query() or None
            return rt.build_general_ledger(self._service.general_ledger(period, code))
        if key == "trial":
            return rt.build_trial_balance(self._service.trial_balance(period))
        if key == "income":
            return rt.build_income_statement(self._service.income_statement(period))
        if key == "balance":
            return rt.build_balance_sheet(self._service.balance_sheet(period.end))
        if key == "cashflow":
            return rt.build_cash_flow(self._service.cash_flow(period))
        if key == "debt_ar":
            return rt.build_debt_summary(self._service.debt_summary(
                period, "131", account_label="131 — Phải thu khách hàng",
                debit_positive=True,
            ))
        if key == "debt_ap":
            return rt.build_debt_summary(self._service.debt_summary(
                period, "331", account_label="331 — Phải trả người bán",
                debit_positive=False,
            ))
        return rt.build_general_journal(self._service.general_journal(period))
