"""Report value objects: the computed outputs of :mod:`ReportService`.

These are *derived* read-models — they are never persisted. Every amount is a
:class:`~decimal.Decimal` so totals stay exact through Excel/PDF export.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

_ZERO = Decimal("0")


@dataclass(frozen=True)
class ReportPeriod:
    """An inclusive ``[start, end]`` reporting window."""
    start: date
    end: date

    @property
    def label(self) -> str:
        return f"{self.start.strftime('%d/%m/%Y')} – {self.end.strftime('%d/%m/%Y')}"


# --- Sổ nhật ký chung (General Journal) -----------------------------------


@dataclass
class JournalLedgerRow:
    """One posting line on the flat General Journal timeline."""
    entry_date: date
    ref: str
    description: str
    account_code: str
    account_name: str
    debit: Decimal = field(default_factory=lambda: _ZERO)
    credit: Decimal = field(default_factory=lambda: _ZERO)


@dataclass
class GeneralJournal:
    period: ReportPeriod
    rows: list[JournalLedgerRow] = field(default_factory=list)

    @property
    def total_debit(self) -> Decimal:
        return sum((r.debit for r in self.rows), _ZERO)

    @property
    def total_credit(self) -> Decimal:
        return sum((r.credit for r in self.rows), _ZERO)

    @property
    def is_balanced(self) -> bool:
        return self.total_debit == self.total_credit


# --- Bảng cân đối tài khoản (Trial Balance) -------------------------------


@dataclass
class TrialBalanceRow:
    code: str
    name: str
    opening_debit: Decimal = field(default_factory=lambda: _ZERO)
    opening_credit: Decimal = field(default_factory=lambda: _ZERO)
    period_debit: Decimal = field(default_factory=lambda: _ZERO)
    period_credit: Decimal = field(default_factory=lambda: _ZERO)
    closing_debit: Decimal = field(default_factory=lambda: _ZERO)
    closing_credit: Decimal = field(default_factory=lambda: _ZERO)


@dataclass
class TrialBalance:
    period: ReportPeriod
    rows: list[TrialBalanceRow] = field(default_factory=list)

    def _sum(self, attr: str) -> Decimal:
        return sum((getattr(r, attr) for r in self.rows), _ZERO)

    @property
    def total_opening_debit(self) -> Decimal:
        return self._sum("opening_debit")

    @property
    def total_opening_credit(self) -> Decimal:
        return self._sum("opening_credit")

    @property
    def total_period_debit(self) -> Decimal:
        return self._sum("period_debit")

    @property
    def total_period_credit(self) -> Decimal:
        return self._sum("period_credit")

    @property
    def total_closing_debit(self) -> Decimal:
        return self._sum("closing_debit")

    @property
    def total_closing_credit(self) -> Decimal:
        return self._sum("closing_credit")

    @property
    def is_balanced(self) -> bool:
        """A trial balance is sound when every column pair self-balances."""
        return (
            self.total_opening_debit == self.total_opening_credit
            and self.total_period_debit == self.total_period_credit
            and self.total_closing_debit == self.total_closing_credit
        )


# --- Sổ cái / Sổ chi tiết tài khoản (General Ledger) ----------------------


@dataclass
class GeneralLedgerRow:
    """One posting line within a single account's ledger, with running balance.

    ``counter_account`` is the opposite-side account(s) of the same entry — the
    "tài khoản đối ứng" column. ``balance`` is the signed net balance
    (debit − credit, debit-positive) of the account *after* this line.
    """
    entry_date: date
    ref: str
    description: str
    counter_account: str
    debit: Decimal = field(default_factory=lambda: _ZERO)
    credit: Decimal = field(default_factory=lambda: _ZERO)
    balance: Decimal = field(default_factory=lambda: _ZERO)
    # Tên đối tượng công nợ (khách hàng / nhà cung cấp) của dòng, nếu có.
    partner_name: str = ""


@dataclass
class GeneralLedgerAccount:
    """All in-period postings to one account, bracketed by opening/closing."""
    code: str
    name: str
    opening_balance: Decimal = field(default_factory=lambda: _ZERO)
    rows: list[GeneralLedgerRow] = field(default_factory=list)

    @property
    def total_debit(self) -> Decimal:
        return sum((r.debit for r in self.rows), _ZERO)

    @property
    def total_credit(self) -> Decimal:
        return sum((r.credit for r in self.rows), _ZERO)

    @property
    def closing_balance(self) -> Decimal:
        return self.opening_balance + self.total_debit - self.total_credit


@dataclass
class GeneralLedger:
    """Sổ cái — one :class:`GeneralLedgerAccount` section per account."""
    period: ReportPeriod
    accounts: list[GeneralLedgerAccount] = field(default_factory=list)

    @property
    def is_balanced(self) -> bool:
        """A complete ledger self-balances: signed closing balances net to zero."""
        return sum((a.closing_balance for a in self.accounts), _ZERO) == _ZERO


# --- Báo cáo tài chính (Financial Statements) -----------------------------


@dataclass
class StatementLine:
    code: str
    label: str
    amount: Decimal = field(default_factory=lambda: _ZERO)


@dataclass
class IncomeStatement:
    """Báo cáo kết quả hoạt động kinh doanh (P&L)."""
    period: ReportPeriod
    revenue_lines: list[StatementLine] = field(default_factory=list)
    expense_lines: list[StatementLine] = field(default_factory=list)

    @property
    def total_revenue(self) -> Decimal:
        return sum((l.amount for l in self.revenue_lines), _ZERO)

    @property
    def total_expense(self) -> Decimal:
        return sum((l.amount for l in self.expense_lines), _ZERO)

    @property
    def profit_before_tax(self) -> Decimal:
        return self.total_revenue - self.total_expense


@dataclass
class BalanceSheet:
    """Bảng cân đối kế toán as of a single date."""
    as_of: date
    asset_lines: list[StatementLine] = field(default_factory=list)
    liability_lines: list[StatementLine] = field(default_factory=list)
    equity_lines: list[StatementLine] = field(default_factory=list)
    # Undistributed current-period result, folded into the equity side so the
    # sheet balances before the year-end close to 421 is posted.
    result_profit: Decimal = field(default_factory=lambda: _ZERO)

    @property
    def total_assets(self) -> Decimal:
        return sum((l.amount for l in self.asset_lines), _ZERO)

    @property
    def total_liabilities(self) -> Decimal:
        return sum((l.amount for l in self.liability_lines), _ZERO)

    @property
    def total_equity(self) -> Decimal:
        return sum((l.amount for l in self.equity_lines), _ZERO) + self.result_profit

    @property
    def total_capital(self) -> Decimal:
        """Tổng nguồn vốn = nợ phải trả + vốn chủ sở hữu."""
        return self.total_liabilities + self.total_equity

    @property
    def is_balanced(self) -> bool:
        return self.total_assets == self.total_capital


# --- Bảng tổng hợp công nợ (Debt summary — AR 131 / AP 331) ---------------


@dataclass
class DebtSummaryRow:
    """One đối tượng (khách hàng / nhà cung cấp) on the debt summary.

    ``opening``/``debit``/``credit`` are raw signed sums from posted journal
    lines (debit-positive). ``closing`` follows the ledger identity; the report's
    ``debit_positive`` flag tells the builder which sign reads as "họ nợ mình" so
    AR and AP both print positive outstanding balances.
    """
    partner_code: str
    partner_name: str
    opening: Decimal = field(default_factory=lambda: _ZERO)
    debit: Decimal = field(default_factory=lambda: _ZERO)
    credit: Decimal = field(default_factory=lambda: _ZERO)

    @property
    def closing(self) -> Decimal:
        return self.opening + self.debit - self.credit


@dataclass
class DebtSummary:
    """Bảng tổng hợp công nợ phải thu (131) hoặc phải trả (331) theo đối tượng."""
    period: ReportPeriod
    account_label: str
    debit_positive: bool = True
    rows: list[DebtSummaryRow] = field(default_factory=list)

    @property
    def total_opening(self) -> Decimal:
        return sum((r.opening for r in self.rows), _ZERO)

    @property
    def total_debit(self) -> Decimal:
        return sum((r.debit for r in self.rows), _ZERO)

    @property
    def total_credit(self) -> Decimal:
        return sum((r.credit for r in self.rows), _ZERO)

    @property
    def total_closing(self) -> Decimal:
        return sum((r.closing for r in self.rows), _ZERO)


@dataclass
class CashFlowRow:
    entry_date: date
    ref: str
    description: str
    inflow: Decimal = field(default_factory=lambda: _ZERO)
    outflow: Decimal = field(default_factory=lambda: _ZERO)


@dataclass
class CashFlow:
    """Báo cáo lưu chuyển tiền tệ (direct view of cash-account movements)."""
    period: ReportPeriod
    opening_balance: Decimal = field(default_factory=lambda: _ZERO)
    rows: list[CashFlowRow] = field(default_factory=list)

    @property
    def total_inflow(self) -> Decimal:
        return sum((r.inflow for r in self.rows), _ZERO)

    @property
    def total_outflow(self) -> Decimal:
        return sum((r.outflow for r in self.rows), _ZERO)

    @property
    def net_change(self) -> Decimal:
        return self.total_inflow - self.total_outflow

    @property
    def closing_balance(self) -> Decimal:
        return self.opening_balance + self.net_change