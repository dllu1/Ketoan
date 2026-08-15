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
    # Tài khoản tổng hợp: ``parent_code`` là mã cha (rỗng = tài khoản gốc);
    # ``level`` là độ sâu trong cây (gốc = 0) để thụt lề khi hiển thị. Số của
    # dòng cha đã cộng gộp cả con nên tổng cột chỉ cộng các dòng gốc.
    parent_code: str = ""
    level: int = 0
    is_aggregate: bool = False


@dataclass
class TrialBalance:
    period: ReportPeriod
    rows: list[TrialBalanceRow] = field(default_factory=list)

    def _sum(self, attr: str) -> Decimal:
        # Chỉ cộng các dòng gốc (không có tài khoản cha): số dư dòng cha đã gộp
        # cả con, nên cộng cả cha lẫn con sẽ tính trùng. Khi chưa khai báo tổng
        # hợp nào thì mọi dòng đều là gốc → tổng không đổi so với trước.
        return sum((getattr(r, attr) for r in self.rows if not r.parent_code), _ZERO)

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


# --- Báo cáo lập theo mẫu in ("Mã số" chỉ tiêu) ---------------------------


@dataclass(frozen=True)
class StatementIndicator:
    """Một dòng trên mẫu in (B02-DNN, B03-DNN): tên chỉ tiêu + "Mã số"."""
    label: str
    code: str = ""            # "" cho dòng tiêu đề mục (I, II, III)
    is_section: bool = False  # tiêu đề mục — không có số liệu
    is_total: bool = False    # dòng cộng — in đậm


@dataclass
class IndicatorStatement:
    """Báo cáo tra số theo "Mã số", hai cột Năm nay / Năm trước.

    ``current``/``prior`` là số tiền của từng mã số; khung chỉ tiêu (nhãn, thứ
    tự, dòng cộng) nằm ở hằng ``*_INDICATORS`` tương ứng, còn công thức cộng ở
    ``*_SUBTOTALS`` — nên sửa nhãn mẫu in không đụng tới cách tính.
    """
    period: ReportPeriod
    prior_period: ReportPeriod | None = None
    current: dict[str, Decimal] = field(default_factory=dict)
    prior: dict[str, Decimal] = field(default_factory=dict)

    def amount(self, code: str, *, prior: bool = False) -> Decimal:
        source = self.prior if prior else self.current
        return source.get(code, _ZERO)


# --- Báo cáo lưu chuyển tiền tệ — Mẫu số B03-DNN (trực tiếp) --------------


# Khung cố định của mẫu số B03-DNN (ban hành theo TT133/2016/TT-BTC) lập theo
# phương pháp trực tiếp. Chỉ là bố cục — giá trị từng "Mã số" do
# :meth:`~domain.services.report_service.ReportService.cash_flow_statement`
# tính từ sổ, nên sửa nhãn ở đây không ảnh hưởng cách tính.
CASH_FLOW_INDICATORS: tuple[StatementIndicator, ...] = (
    StatementIndicator("I. Lưu chuyển tiền từ hoạt động kinh doanh", is_section=True),
    StatementIndicator(
        "1. Tiền thu từ bán hàng, cung cấp dịch vụ và doanh thu khác", "01"),
    StatementIndicator("2. Tiền chi trả cho người cung cấp hàng hóa, dịch vụ", "02"),
    StatementIndicator("3. Tiền chi trả cho người lao động", "03"),
    StatementIndicator("4. Tiền lãi vay đã trả", "04"),
    StatementIndicator("5. Thuế thu nhập doanh nghiệp đã nộp", "05"),
    StatementIndicator("6. Tiền thu khác từ hoạt động kinh doanh", "06"),
    StatementIndicator("7. Tiền chi khác cho hoạt động kinh doanh", "07"),
    StatementIndicator(
        "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "20", is_total=True),

    StatementIndicator("II. Lưu chuyển tiền từ hoạt động đầu tư", is_section=True),
    StatementIndicator(
        "1. Tiền chi để mua sắm, xây dựng TSCĐ, BĐSĐT và các tài sản dài hạn khác",
        "21"),
    StatementIndicator(
        "2. Tiền thu từ thanh lý, nhượng bán TSCĐ, BĐSĐT và các tài sản dài hạn khác",
        "22"),
    StatementIndicator("3. Tiền chi cho vay, đầu tư góp vốn vào đơn vị khác", "23"),
    StatementIndicator(
        "4. Tiền thu hồi cho vay, đầu tư góp vốn vào đơn vị khác", "24"),
    StatementIndicator(
        "5. Tiền thu lãi cho vay, cổ tức và lợi nhuận được chia", "25"),
    StatementIndicator(
        "Lưu chuyển tiền thuần từ hoạt động đầu tư", "30", is_total=True),

    StatementIndicator("III. Lưu chuyển tiền từ hoạt động tài chính", is_section=True),
    StatementIndicator(
        "1. Tiền thu từ phát hành cổ phiếu, nhận vốn góp của chủ sở hữu", "31"),
    StatementIndicator(
        "2. Tiền trả lại vốn góp cho các chủ sở hữu, mua lại cổ phiếu của doanh "
        "nghiệp đã phát hành", "32"),
    StatementIndicator("3. Tiền thu từ đi vay", "33"),
    StatementIndicator("4. Tiền trả nợ gốc vay và nợ gốc thuê tài chính", "34"),
    StatementIndicator("5. Cổ tức, lợi nhuận đã trả cho chủ sở hữu", "35"),
    StatementIndicator(
        "Lưu chuyển tiền thuần từ hoạt động tài chính", "40", is_total=True),

    StatementIndicator(
        "Lưu chuyển tiền thuần trong kỳ (50 = 20+30+40)", "50", is_total=True),
    StatementIndicator("Tiền và tương đương tiền đầu kỳ", "60"),
    StatementIndicator(
        "Ảnh hưởng của thay đổi tỷ giá hối đoái quy đổi ngoại tệ", "61"),
    StatementIndicator(
        "Tiền và tương đương tiền cuối kỳ (70 = 50+60+61)", "70", is_total=True),
)

# Chỉ tiêu cộng → các mã thành phần. Thứ tự khai báo cũng là thứ tự tính:
# [50] cần [20]/[30]/[40] đã cộng xong, [70] cần [50].
CASH_FLOW_SUBTOTALS: dict[str, tuple[str, ...]] = {
    "20": ("01", "02", "03", "04", "05", "06", "07"),
    "30": ("21", "22", "23", "24", "25"),
    "40": ("31", "32", "33", "34", "35"),
    "50": ("20", "30", "40"),
    "70": ("50", "60", "61"),
}


@dataclass
class CashFlowStatement(IndicatorStatement):
    """Báo cáo lưu chuyển tiền tệ theo mẫu B03-DNN (phương pháp trực tiếp).

    Tiền thu mang dấu dương, tiền chi mang dấu âm — đúng như mẫu in (các dòng
    chi hiện trong ngoặc đơn), nên mọi chỉ tiêu cộng đều là phép cộng thuần.
    """


# --- Báo cáo kết quả hoạt động kinh doanh — Mẫu số B02-DNN ----------------


INCOME_STATEMENT_INDICATORS: tuple[StatementIndicator, ...] = (
    StatementIndicator("1. Doanh thu bán hàng và cung cấp dịch vụ", "01"),
    StatementIndicator("2. Các khoản giảm trừ doanh thu", "02"),
    StatementIndicator(
        "3. Doanh thu thuần về bán hàng và cung cấp dịch vụ (10 = 01 - 02)",
        "10", is_total=True),
    StatementIndicator("4. Giá vốn hàng bán", "11"),
    StatementIndicator(
        "5. Lợi nhuận gộp về bán hàng và cung cấp dịch vụ (20 = 10 - 11)",
        "20", is_total=True),
    StatementIndicator("6. Doanh thu hoạt động tài chính", "21"),
    StatementIndicator("7. Chi phí tài chính", "22"),
    StatementIndicator("        Trong đó: Chi phí lãi vay", "23"),
    StatementIndicator("8. Chi phí quản lý kinh doanh", "24"),
    StatementIndicator(
        "9. Lợi nhuận thuần từ hoạt động kinh doanh (30 = 20 + 21 - 22 - 24)",
        "30", is_total=True),
    StatementIndicator("10. Thu nhập khác", "31"),
    StatementIndicator("11. Chi phí khác", "32"),
    StatementIndicator("12. Lợi nhuận khác (40 = 31 - 32)", "40", is_total=True),
    StatementIndicator(
        "13. Tổng lợi nhuận kế toán trước thuế (50 = 30 + 40)", "50", is_total=True),
    StatementIndicator("14. Chi phí thuế thu nhập doanh nghiệp", "51"),
    StatementIndicator(
        "15. Lợi nhuận sau thuế thu nhập doanh nghiệp (60 = 50 - 51)",
        "60", is_total=True),
)

# Khác B03-DNN: trên mẫu B02 các dòng chi phí in số dương, nên công thức cộng
# phải mang dấu — (mã số, dấu). Thứ tự khai báo là thứ tự tính.
INCOME_STATEMENT_SUBTOTALS: dict[str, tuple[tuple[str, int], ...]] = {
    "10": (("01", 1), ("02", -1)),
    "20": (("10", 1), ("11", -1)),
    "30": (("20", 1), ("21", 1), ("22", -1), ("24", -1)),
    "40": (("31", 1), ("32", -1)),
    "50": (("30", 1), ("40", 1)),
    "60": (("50", 1), ("51", -1)),
}


@dataclass
class IncomeStatementB02(IndicatorStatement):
    """Báo cáo kết quả hoạt động kinh doanh theo mẫu B02-DNN.

    Doanh thu và chi phí đều in số dương như mẫu; chỉ các dòng lợi nhuận mới
    có thể âm (lỗ). Khác :class:`IncomeStatement` — bảng liệt kê theo từng tài
    khoản dùng để dò sổ, không phải mẫu nộp.
    """