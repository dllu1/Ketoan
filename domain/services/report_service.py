"""ReportService: derives financial reports from POSTED journal entries.

The General Journal is the single source of truth. Every report here is a pure
aggregation over journal lines — no separate balances are stored, so reports can
never drift out of sync with the ledger. Only :class:`EntryStatus.POSTED`
entries count; drafts are excluded.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from data.repositories.account_repo import AccountRepository
from data.repositories.journal_repo import JournalRepository
from data.repositories.partner_repo import PartnerRepository
from domain.models.account import Account, AccountKind
from domain.services.opening_service import OpeningBalanceService
from domain.models.journal import EntryStatus, JournalEntry, JournalLine
from domain.models.report import (
    BalanceSheet,
    CashFlow,
    CashFlowRow,
    DebtSummary,
    DebtSummaryRow,
    GeneralJournal,
    GeneralLedger,
    GeneralLedgerAccount,
    GeneralLedgerRow,
    IncomeStatement,
    JournalLedgerRow,
    ReportPeriod,
    StatementLine,
    TrialBalance,
    TrialBalanceRow,
)

_ZERO = Decimal("0")

# Tiền mặt (111) · Tiền gửi ngân hàng (112) · Tiền đang chuyển (113).
_CASH_PREFIXES = ("111", "112", "113")

# Fallback classification by leading digit when an account is absent from the
# chart of accounts (Vietnamese TT133/TT200 numbering).
_KIND_BY_DIGIT = {
    "1": AccountKind.ASSET,
    "2": AccountKind.ASSET,
    "3": AccountKind.LIABILITY,
    "4": AccountKind.EQUITY,
    "5": AccountKind.REVENUE,
    "6": AccountKind.EXPENSE,
    "7": AccountKind.REVENUE,
    "8": AccountKind.EXPENSE,
    "9": AccountKind.OTHER,   # 911 — xác định kết quả kinh doanh
}


class ReportService:
    def __init__(
        self,
        journal_repo: JournalRepository,
        account_repo: AccountRepository | None = None,
        opening_service: OpeningBalanceService | None = None,
        partner_repo: PartnerRepository | None = None,
    ) -> None:
        self._journal = journal_repo
        self._accounts = account_repo or AccountRepository()
        self._opening = opening_service or OpeningBalanceService()
        self._partners = partner_repo or PartnerRepository()

    # ----- public reports ---------------------------------------------------

    def general_journal(self, period: ReportPeriod) -> GeneralJournal:
        report = GeneralJournal(period=period)
        for entry in self._posted_in_range(period.start, period.end):
            for line in entry.lines:
                report.rows.append(
                    JournalLedgerRow(
                        entry_date=entry.entry_date,
                        ref=entry.ref,
                        description=line.description or entry.description,
                        account_code=line.account_code,
                        account_name=self._name_for(line.account_code, line.account_name),
                        debit=line.debit,
                        credit=line.credit,
                    )
                )
        return report

    def general_ledger(
        self, period: ReportPeriod, account_code: str | None = None
    ) -> GeneralLedger:
        """Sổ cái — per-account ledger with opening, running and closing balances.

        With ``account_code`` set, only that account's section is built (Sổ chi
        tiết một tài khoản); otherwise every account with an opening balance or
        in-period movement gets a section, ordered by code. Like every report
        here it is a pure aggregation over POSTED journal lines.
        """
        opening = self._net_balances(before=period.start)
        entries = self._posted_in_range(period.start, period.end)

        active = {l.account_code for e in entries for l in e.lines}
        codes = set(opening) | active
        if account_code:
            # Tìm theo số tài khoản: khớp tiền tố/chuỗi con để gõ "131" ra cả
            # 131, 1311… Rỗng/None → toàn bộ sổ cái.
            needle = account_code.strip()
            codes = {c for c in codes if needle in c}

        # Một lượt quét sổ thay vì lồng (mã TK × bút toán × dòng): dựng sẵn một
        # GeneralLedgerAccount cho mỗi mã rồi phân dòng vào đúng tài khoản, giữ
        # số dư lũy kế riêng cho từng mã. Trước đây với N tài khoản × M bút toán
        # là O(N·M); nay là O(số dòng) — mượt hẳn khi dựng Sổ cái toàn bộ.
        ledgers: dict[str, GeneralLedgerAccount] = {}
        balances: dict[str, Decimal] = {}
        for code in codes:
            open_net = opening.get(code, _ZERO)
            ledgers[code] = GeneralLedgerAccount(
                code=code, name=self._name_for(code), opening_balance=open_net
            )
            balances[code] = open_net

        for entry in entries:
            for line in entry.lines:
                ledger = ledgers.get(line.account_code)
                if ledger is None:
                    continue
                balance = balances[line.account_code] + line.debit - line.credit
                balances[line.account_code] = balance
                ledger.rows.append(
                    GeneralLedgerRow(
                        entry_date=entry.entry_date,
                        ref=entry.ref,
                        description=line.description or entry.description,
                        counter_account=self._counter_accounts(entry, line),
                        debit=line.debit,
                        credit=line.credit,
                        balance=balance,
                        partner_name=self._partner_name(line.partner_code),
                    )
                )

        report = GeneralLedger(period=period)
        for code in sorted(codes):
            ledger = ledgers[code]
            if ledger.opening_balance == _ZERO and not ledger.rows:
                continue
            report.accounts.append(ledger)
        return report

    def trial_balance(self, period: ReportPeriod) -> TrialBalance:
        opening = self._net_balances(before=period.start)
        movements = self._movements(period.start, period.end)

        codes = sorted(set(opening) | set(movements))
        report = TrialBalance(period=period)
        for code in codes:
            open_net = opening.get(code, _ZERO)
            debit, credit = movements.get(code, (_ZERO, _ZERO))
            close_net = open_net + debit - credit
            if open_net == _ZERO and debit == _ZERO and credit == _ZERO:
                continue
            report.rows.append(
                TrialBalanceRow(
                    code=code,
                    name=self._name_for(code),
                    opening_debit=open_net if open_net > 0 else _ZERO,
                    opening_credit=-open_net if open_net < 0 else _ZERO,
                    period_debit=debit,
                    period_credit=credit,
                    closing_debit=close_net if close_net > 0 else _ZERO,
                    closing_credit=-close_net if close_net < 0 else _ZERO,
                )
            )
        return report

    def income_statement(self, period: ReportPeriod) -> IncomeStatement:
        movements = self._movements(period.start, period.end)
        statement = IncomeStatement(period=period)
        for code in sorted(movements):
            debit, credit = movements[code]
            kind = self._kind_for(code)
            if kind is AccountKind.REVENUE:
                amount = credit - debit          # doanh thu thuần (net credit)
                if amount != _ZERO:
                    statement.revenue_lines.append(
                        StatementLine(code, self._name_for(code), amount)
                    )
            elif kind is AccountKind.EXPENSE:
                amount = debit - credit          # chi phí (net debit)
                if amount != _ZERO:
                    statement.expense_lines.append(
                        StatementLine(code, self._name_for(code), amount)
                    )
        return statement

    def balance_sheet(self, as_of: date) -> BalanceSheet:
        # Inclusive of as_of: balances accumulate up to and including that day.
        balances = self._net_balances(before=_day_after(as_of))
        sheet = BalanceSheet(as_of=as_of)
        result = _ZERO
        for code in sorted(balances):
            net = balances[code]
            if net == _ZERO:
                continue
            kind = self._kind_for(code)
            if kind is AccountKind.ASSET:
                sheet.asset_lines.append(StatementLine(code, self._name_for(code), net))
            elif kind is AccountKind.LIABILITY:
                sheet.liability_lines.append(
                    StatementLine(code, self._name_for(code), -net)
                )
            elif kind is AccountKind.EQUITY:
                sheet.equity_lines.append(
                    StatementLine(code, self._name_for(code), -net)
                )
            elif kind is AccountKind.REVENUE:
                result += -net                    # net credit adds to profit
            elif kind is AccountKind.EXPENSE:
                result += -net                    # net debit subtracts from profit
        sheet.result_profit = result
        return sheet

    def debt_summary(
        self,
        period: ReportPeriod,
        account_prefix: str,
        *,
        account_label: str = "",
        debit_positive: bool = True,
    ) -> DebtSummary:
        """Bảng tổng hợp công nợ theo đối tượng cho nhóm TK ``account_prefix``.

        Pure aggregation over POSTED journal lines whose account starts with
        ``account_prefix`` (vd: "131" phải thu, "331" phải trả), grouped by the
        line's ``partner_code``. Opening is the net (Nợ − Có) of that đối tượng
        before the period; phát sinh Nợ/Có are the gross in-period sums. A line
        with no partner tag is grouped under "Không xác định" so nothing is lost.
        Số dư đầu kỳ ở đây tính từ các bút toán đã ghi sổ (số dư đầu kỳ khai báo
        không gắn đối tượng nên không phân bổ được cho từng KH/NCC).
        """
        opening: dict[str, Decimal] = {}
        debit: dict[str, Decimal] = {}
        credit: dict[str, Decimal] = {}
        for entry in self._all_entries():
            if entry.status is not EntryStatus.POSTED:
                continue
            in_range = period.start <= entry.entry_date <= period.end
            before = entry.entry_date < period.start
            if not (in_range or before):
                continue
            for line in entry.lines:
                if not line.account_code.startswith(account_prefix):
                    continue
                key = line.partner_code or ""
                if before:
                    opening[key] = opening.get(key, _ZERO) + line.debit - line.credit
                else:
                    debit[key] = debit.get(key, _ZERO) + line.debit
                    credit[key] = credit.get(key, _ZERO) + line.credit

        report = DebtSummary(
            period=period,
            account_label=account_label or account_prefix,
            debit_positive=debit_positive,
        )
        for key in set(opening) | set(debit) | set(credit):
            o = opening.get(key, _ZERO)
            d = debit.get(key, _ZERO)
            c = credit.get(key, _ZERO)
            if o == _ZERO and d == _ZERO and c == _ZERO:
                continue
            report.rows.append(
                DebtSummaryRow(
                    partner_code=key,
                    partner_name=self._partner_name(key) if key else "Không xác định",
                    opening=o,
                    debit=d,
                    credit=c,
                )
            )
        report.rows.sort(key=lambda r: (r.partner_name, r.partner_code))
        return report

    def cash_flow(self, period: ReportPeriod) -> CashFlow:
        opening = _ZERO
        for code, net in self._net_balances(before=period.start).items():
            if self._is_cash(code):
                opening += net

        report = CashFlow(period=period, opening_balance=opening)
        for entry in self._posted_in_range(period.start, period.end):
            cash_debit = sum(
                (l.debit for l in entry.lines if self._is_cash(l.account_code)), _ZERO
            )
            cash_credit = sum(
                (l.credit for l in entry.lines if self._is_cash(l.account_code)), _ZERO
            )
            if cash_debit == _ZERO and cash_credit == _ZERO:
                continue
            report.rows.append(
                CashFlowRow(
                    entry_date=entry.entry_date,
                    ref=entry.ref,
                    description=entry.description,
                    inflow=cash_debit,
                    outflow=cash_credit,
                )
            )
        return report

    # ----- aggregation helpers ---------------------------------------------

    def _all_entries(self) -> list[JournalEntry]:
        """Quét sổ một lần cho mỗi báo cáo.

        Nhiều báo cáo cần cả số dư đầu kỳ (_net_balances) lẫn phát sinh trong kỳ
        (_posted_in_range) — trước đây mỗi lần gọi lại quét toàn bộ sổ. Cache theo
        instance an toàn vì màn hình dựng ReportService mới cho mỗi lần làm mới
        (giống _acc_cache), nên không bao giờ lỗi thời sau khi ghi sổ.
        """
        cached = getattr(self, "_entries_cache", None)
        if cached is None:
            cached = self._journal.list_all()
            self._entries_cache = cached
        return cached

    def _posted_in_range(self, start: date, end: date) -> list[JournalEntry]:
        entries = [
            e for e in self._all_entries()
            if e.status is EntryStatus.POSTED and start <= e.entry_date <= end
        ]
        entries.sort(key=lambda e: (e.entry_date, e.ref))
        return entries

    def _net_balances(self, *, before: date) -> dict[str, Decimal]:
        """Net (debit − credit) per account for postings strictly before *before*.

        On top of the journal-derived total, declared opening balances (số dư đầu
        kỳ) already in effect by *before* are added as a baseline — this is what
        makes a report show an opening when the prior period has no postings.
        """
        net: dict[str, Decimal] = dict(self._opening_baseline(before))
        for entry in self._all_entries():
            if entry.status is not EntryStatus.POSTED or entry.entry_date >= before:
                continue
            for line in entry.lines:
                net[line.account_code] = (
                    net.get(line.account_code, _ZERO) + line.debit - line.credit
                )
        return net

    def _opening_baseline(self, before: date) -> dict[str, Decimal]:
        """Declared opening balances in effect by *before* (cached per instance)."""
        cache = getattr(self, "_opening_cache", None)
        if cache is None:
            cache = {}
            self._opening_cache = cache
        if before not in cache:
            cache[before] = self._opening.baseline_before(before)
        return cache[before]

    def _movements(self, start: date, end: date) -> dict[str, tuple[Decimal, Decimal]]:
        """Gross (debit, credit) per account for postings within ``[start, end]``."""
        moves: dict[str, tuple[Decimal, Decimal]] = {}
        for entry in self._posted_in_range(start, end):
            for line in entry.lines:
                debit, credit = moves.get(line.account_code, (_ZERO, _ZERO))
                moves[line.account_code] = (debit + line.debit, credit + line.credit)
        return moves

    # ----- chart-of-accounts lookups ---------------------------------------

    def _account_map(self) -> dict[str, Account]:
        cached = getattr(self, "_acc_cache", None)
        if cached is None:
            cached = {a.code: a for a in self._accounts.list_all()}
            self._acc_cache = cached
        return cached

    def _name_for(self, code: str, fallback: str = "") -> str:
        account = self._account_map().get(code)
        if account:
            return account.name
        # Sub-account (e.g. 1111) inherits its parent's name when unmapped.
        parent = self._account_map().get(code[:3])
        if parent:
            return parent.name
        return fallback or code

    def _partner_map(self) -> dict[str, str]:
        cached = getattr(self, "_partner_cache", None)
        if cached is None:
            cached = {p.code: p.name for p in self._partners.list_all()}
            self._partner_cache = cached
        return cached

    def _partner_name(self, code: str) -> str:
        if not code:
            return ""
        return self._partner_map().get(code, code)

    def _kind_for(self, code: str) -> AccountKind:
        account = self._account_map().get(code) or self._account_map().get(code[:3])
        if account and account.kind:
            try:
                return AccountKind(account.kind)
            except ValueError:
                pass
        return _KIND_BY_DIGIT.get(code[:1], AccountKind.OTHER)

    @staticmethod
    def _is_cash(code: str) -> bool:
        return code.startswith(_CASH_PREFIXES)

    @staticmethod
    def _counter_accounts(entry: JournalEntry, line: JournalLine) -> str:
        """Opposite-side account code(s) of *line* within *entry* (TK đối ứng).

        A debit line is offset by the entry's credit lines and vice versa;
        codes are de-duplicated keeping first-seen order and joined with ", ".
        """
        if line.debit > _ZERO:
            others = [l.account_code for l in entry.lines if l.credit > _ZERO]
        elif line.credit > _ZERO:
            others = [l.account_code for l in entry.lines if l.debit > _ZERO]
        else:
            others = []
        seen: list[str] = []
        for code in others:
            if code not in seen:
                seen.append(code)
        return ", ".join(seen)


def _day_after(value: date) -> date:
    return value + timedelta(days=1)