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
from domain.services import account_hierarchy
from domain.services.opening_service import OpeningBalanceService
from domain.services.transfer_rule_service import TransferRuleService
from domain.models.journal import EntryStatus, JournalEntry, JournalLine
from domain.models.report import (
    CASH_FLOW_SUBTOTALS,
    INCOME_STATEMENT_SUBTOTALS,
    BalanceSheet,
    CashFlow,
    CashFlowRow,
    CashFlowStatement,
    IncomeStatementB02,
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

# --- Phân loại dòng tiền cho mẫu B03-DNN ----------------------------------
# Tài khoản đối ứng của khoản tiền (bên Có khi thu, bên Nợ khi chi) → "Mã số"
# trên mẫu. Dò theo tiền tố 4 ký tự trước rồi 3 ký tự, nên 3334 (thuế TNDN đã
# nộp) thắng nhóm 333 chung, và 1331 rơi về 133.
_B03_INFLOW = {
    "511": "01", "512": "01", "131": "01", "3331": "01", "3387": "01",
    "515": "25",
    "211": "22", "213": "22", "217": "22", "241": "22",
    "121": "24", "128": "24", "171": "24", "221": "24", "222": "24", "228": "24",
    "411": "31", "419": "31",
    "341": "33",
}
_B03_INFLOW_DEFAULT = "06"        # thu khác từ hoạt động kinh doanh

_B03_OUTFLOW = {
    "133": "02", "151": "02", "152": "02", "153": "02", "154": "02", "155": "02",
    "156": "02", "157": "02", "242": "02", "331": "02", "611": "02", "621": "02",
    "622": "02", "623": "02", "627": "02", "641": "02", "642": "02",
    "334": "03",
    "635": "04",
    "3334": "05",
    "211": "21", "213": "21", "217": "21", "241": "21",
    "121": "23", "128": "23", "171": "23", "221": "23", "222": "23", "228": "23",
    "411": "32", "419": "32",
    "341": "34",
    "421": "35",
}
_B03_OUTFLOW_DEFAULT = "07"       # chi khác cho hoạt động kinh doanh

# --- Nhóm tài khoản cho mẫu B02-DNN ---------------------------------------
# TK doanh thu bán hàng: bên Có lên [01], bên Nợ (chiết khấu, giảm giá, hàng
# bán bị trả lại — TT133 ghi thẳng vào 511) lên [02].
_B02_REVENUE = ("511", "512")
_B02_DEDUCTION = ("521",)         # TT200 mở riêng; TT133 thường để trống
_B02_COGS = ("632",)
_B02_FIN_REVENUE = ("515",)
_B02_FIN_EXPENSE = ("635",)
_B02_INTEREST = ("6351",)         # "Trong đó: chi phí lãi vay" — nằm trong [22]
_B02_ADMIN = ("641", "642")       # chi phí bán hàng + QLDN = chi phí QLKD
_B02_OTHER_INCOME = ("711",)
_B02_OTHER_EXPENSE = ("811",)
_B02_CIT_EXPENSE = ("821",)


class ReportService:
    def __init__(
        self,
        journal_repo: JournalRepository,
        account_repo: AccountRepository | None = None,
        opening_service: OpeningBalanceService | None = None,
        partner_repo: PartnerRepository | None = None,
        transfer_rules: TransferRuleService | None = None,
    ) -> None:
        self._journal = journal_repo
        self._accounts = account_repo or AccountRepository()
        self._opening = opening_service or OpeningBalanceService()
        self._partners = partner_repo or PartnerRepository()
        self._rules = transfer_rules or TransferRuleService()

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
        parents = self._parents()
        children = account_hierarchy.children_map(parents)

        # Cộng gộp số dư con vào cha: mỗi cột (dư đầu net, PS Nợ, PS Có) gộp
        # riêng để dòng cha phản ánh đúng tổng các con + số phát sinh riêng của
        # nó. Không có tài khoản tổng hợp nào thì các map giữ nguyên như cũ.
        agg_open = account_hierarchy.aggregate(opening, parents)
        agg_debit = account_hierarchy.aggregate(
            {c: d for c, (d, _c) in movements.items()}, parents
        )
        agg_credit = account_hierarchy.aggregate(
            {c: cr for c, (_d, cr) in movements.items()}, parents
        )

        codes = sorted(set(agg_open) | set(agg_debit) | set(agg_credit))
        report = TrialBalance(period=period)
        for code in codes:
            open_net = agg_open.get(code, _ZERO)
            debit = agg_debit.get(code, _ZERO)
            credit = agg_credit.get(code, _ZERO)
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
                    parent_code=parents.get(code, ""),
                    level=account_hierarchy.depth(code, parents),
                    is_aggregate=code in children,
                )
            )
        return report

    def income_statement(self, period: ReportPeriod) -> IncomeStatement:
        # Bỏ chính các bút toán kết chuyển ra khỏi số phát sinh: sau khi chạy
        # Kết chuyển (F11), TK 511 vừa có Có (doanh thu) vừa có Nợ (KC-DT) nên
        # net = 0 — báo cáo KQKD và tờ khai TNDN sẽ trắng trơn dù sổ vẫn đủ số.
        # Bút toán giá vốn KC-GV *không* bị loại vì nó sinh chi phí 632 thật.
        movements = self._movements(
            period.start, period.end, skip_result_transfers=True
        )
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

    def income_statement_b02(self, period: ReportPeriod) -> IncomeStatementB02:
        """Báo cáo kết quả hoạt động kinh doanh — Mẫu số B02-DNN.

        Khác :meth:`income_statement` (liệt kê từng TK doanh thu/chi phí để dò
        sổ), báo cáo này gom số theo đúng các "Mã số" 01…60 của mẫu in, kèm cột
        Năm trước (cùng khoảng ngày lùi một năm).
        """
        prior = ReportPeriod(
            start=_shift_year(period.start, -1), end=_shift_year(period.end, -1)
        )
        return IncomeStatementB02(
            period=period,
            prior_period=prior,
            current=self._b02_amounts(period),
            prior=self._b02_amounts(prior),
        )

    def _b02_amounts(self, period: ReportPeriod) -> dict[str, Decimal]:
        """Số tiền từng "Mã số" của mẫu B02-DNN trong ``period``.

        Dùng chung nguồn với :meth:`income_statement`: số phát sinh đã loại các
        bút toán kết chuyển sang TK kết quả, nếu không thì sau khi chạy Kết
        chuyển (F11) mọi TK 5xx/6xx đều net về 0 và báo cáo trắng trơn.
        """
        moves = self._movements(period.start, period.end, skip_result_transfers=True)

        def totals(prefixes: tuple[str, ...]) -> tuple[Decimal, Decimal]:
            debit = credit = _ZERO
            for code, (d, c) in moves.items():
                if code.startswith(prefixes):
                    debit += d
                    credit += c
            return debit, credit

        def net_debit(prefixes: tuple[str, ...]) -> Decimal:
            debit, credit = totals(prefixes)
            return debit - credit

        def net_credit(prefixes: tuple[str, ...]) -> Decimal:
            debit, credit = totals(prefixes)
            return credit - debit

        revenue_debit, revenue_credit = totals(_B02_REVENUE)
        values = {
            "01": revenue_credit,
            "02": revenue_debit + net_debit(_B02_DEDUCTION),
            "11": net_debit(_B02_COGS),
            "21": net_credit(_B02_FIN_REVENUE),
            "22": net_debit(_B02_FIN_EXPENSE),
            "23": net_debit(_B02_INTEREST),
            "24": net_debit(_B02_ADMIN),
            "31": net_credit(_B02_OTHER_INCOME),
            "32": net_debit(_B02_OTHER_EXPENSE),
            "51": net_debit(_B02_CIT_EXPENSE),
        }
        for total, parts in INCOME_STATEMENT_SUBTOTALS.items():
            values[total] = sum(
                (values.get(code, _ZERO) * sign for code, sign in parts), _ZERO
            )
        return values

    def balance_sheet(self, as_of: date) -> BalanceSheet:
        # Inclusive of as_of: balances accumulate up to and including that day.
        balances = self._net_balances(before=_day_after(as_of))
        parents = self._parents()
        # Gộp số dư con vào cha rồi chỉ hiển thị tài khoản gốc (không có cha):
        # con đã nằm trong số của cha nên đưa riêng sẽ cộng trùng tổng tài sản /
        # nguồn vốn. Không khai báo tổng hợp thì mọi mã đều là gốc → như cũ.
        balances = account_hierarchy.aggregate(balances, parents)
        sheet = BalanceSheet(as_of=as_of)
        result = _ZERO
        for code in sorted(balances):
            if parents.get(code):
                continue
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

    def net_balances(self, as_of: date) -> dict[str, Decimal]:
        """Số dư net (Nợ − Có) từng mã TK tính đến hết ngày ``as_of``.

        Khác :meth:`aggregated_balances`: **không** gộp con vào cha, nên dùng được
        để soi từng tài khoản một (vd: TK nào còn số dư cuối kỳ).
        """
        return self._net_balances(before=_day_after(as_of))

    def aggregated_balances(self, as_of: date | None = None) -> dict[str, Decimal]:
        """Số dư net theo mã, đã cộng gộp con vào cha (tài khoản tổng hợp).

        Dùng cho màn Danh mục tài khoản để hiển thị cột "Số dư lũy kế": tài
        khoản cha hiện tổng của chính nó và các con. ``as_of=None`` lấy toàn bộ
        lịch sử tới hiện tại.
        """
        before = _day_after(as_of) if as_of else date.max
        return account_hierarchy.aggregate(
            self._net_balances(before=before), self._parents()
        )

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

    def cash_flow_statement(self, period: ReportPeriod) -> CashFlowStatement:
        """Báo cáo lưu chuyển tiền tệ — Mẫu số B03-DNN, phương pháp trực tiếp.

        Khác :meth:`cash_flow` (liệt kê từng phiếu thu/chi như sổ quỹ), báo cáo
        này gom số theo đúng các "Mã số" 01…70 của mẫu in, kèm cột Năm trước
        (cùng khoảng ngày lùi một năm).
        """
        prior = ReportPeriod(
            start=_shift_year(period.start, -1), end=_shift_year(period.end, -1)
        )
        return CashFlowStatement(
            period=period,
            prior_period=prior,
            current=self._b03_amounts(period),
            prior=self._b03_amounts(prior),
        )

    def _b03_amounts(self, period: ReportPeriod) -> dict[str, Decimal]:
        """Số tiền từng "Mã số" của mẫu B03-DNN trong ``period``.

        Mỗi bút toán có động vào TK tiền (111/112/113) được phân loại theo tài
        khoản đối ứng: khoản thu ghi dương, khoản chi ghi âm. Bút toán chỉ
        chuyển tiền giữa các TK tiền (Nợ 112/Có 111) tự triệt tiêu vì không có
        tài khoản đối ứng nào ngoài nhóm tiền.
        """
        values: dict[str, Decimal] = {}

        def add(code: str, amount: Decimal) -> None:
            values[code] = values.get(code, _ZERO) + amount

        for entry in self._posted_in_range(period.start, period.end):
            cash_in = sum(
                (l.debit for l in entry.lines if self._is_cash(l.account_code)), _ZERO
            )
            cash_out = sum(
                (l.credit for l in entry.lines if self._is_cash(l.account_code)), _ZERO
            )
            if cash_in == _ZERO and cash_out == _ZERO:
                continue
            credit_side = [
                (l.account_code, l.credit) for l in entry.lines
                if l.credit > _ZERO and not self._is_cash(l.account_code)
            ]
            debit_side = [
                (l.account_code, l.debit) for l in entry.lines
                if l.debit > _ZERO and not self._is_cash(l.account_code)
            ]
            for code, share in _spread(cash_in, credit_side):
                add(_b03_code(code, _B03_INFLOW, _B03_INFLOW_DEFAULT), share)
            for code, share in _spread(cash_out, debit_side):
                add(_b03_code(code, _B03_OUTFLOW, _B03_OUTFLOW_DEFAULT), -share)

        opening = _ZERO
        for code, net in self._net_balances(before=period.start).items():
            if self._is_cash(code):
                opening += net
        values["60"] = opening
        # [61] chênh lệch tỷ giá: chưa theo dõi ngoại tệ nên luôn bằng 0 — giữ
        # dòng để mẫu in đủ chỉ tiêu và [70] = [50]+[60]+[61] vẫn đúng.
        values.setdefault("61", _ZERO)
        for total, parts in CASH_FLOW_SUBTOTALS.items():
            values[total] = sum((values.get(p, _ZERO) for p in parts), _ZERO)
        return values

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

    def _movements(
        self, start: date, end: date, *, skip_result_transfers: bool = False,
    ) -> dict[str, tuple[Decimal, Decimal]]:
        """Gross (debit, credit) per account for postings within ``[start, end]``.

        ``skip_result_transfers`` bỏ qua các bút toán kết chuyển xác định kết quả
        — nhận diện bằng việc bút toán có dòng ghi vào TK kết quả (mặc định 911).
        """
        moves: dict[str, tuple[Decimal, Decimal]] = {}
        for entry in self._posted_in_range(start, end):
            if skip_result_transfers and self._is_result_transfer(entry):
                continue
            for line in entry.lines:
                debit, credit = moves.get(line.account_code, (_ZERO, _ZERO))
                moves[line.account_code] = (debit + line.debit, credit + line.credit)
        return moves

    def _result_account(self) -> str:
        """Mã TK xác định kết quả kinh doanh đang cấu hình (mặc định 911)."""
        cached = getattr(self, "_result_account_cache", None)
        if cached is None:
            cached = self._rules.result_account().strip()
            self._result_account_cache = cached
        return cached

    def _is_result_transfer(self, entry: JournalEntry) -> bool:
        """Bút toán kết chuyển sang TK kết quả (KC-DT, KC-CP, KC-LN, nhóm tự khai).

        Nhận diện theo tài khoản chứ không theo số chứng từ, vì người dùng đổi
        được tên nhóm quy tắc trong màn hình Kết chuyển.
        """
        result = self._result_account()
        if not result:
            return False
        return any(l.account_code.strip().startswith(result) for l in entry.lines)

    # ----- chart-of-accounts lookups ---------------------------------------

    def _account_map(self) -> dict[str, Account]:
        cached = getattr(self, "_acc_cache", None)
        if cached is None:
            cached = {a.code: a for a in self._accounts.list_all()}
            self._acc_cache = cached
        return cached

    def _parents(self) -> dict[str, str]:
        """Map ``{code: parent_code}`` tài khoản tổng hợp, đã chuẩn hoá + cache."""
        cached = getattr(self, "_parents_cache", None)
        if cached is None:
            accounts = self._account_map()
            raw = {c: a.parent_code for c, a in accounts.items() if a.parent_code}
            cached = account_hierarchy.normalize_parents(raw, accounts.keys())
            self._parents_cache = cached
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


def _shift_year(value: date, delta: int) -> date:
    """Cùng ngày/tháng ở năm khác (29/02 lùi về 28/02 nếu năm đích không nhuận)."""
    try:
        return value.replace(year=value.year + delta)
    except ValueError:
        return value.replace(year=value.year + delta, day=28)


def _b03_code(account_code: str, table: dict[str, str], default: str) -> str:
    """Mã số B03-DNN của một tài khoản đối ứng (tiền tố dài khớp trước)."""
    for length in (4, 3):
        hit = table.get(account_code[:length])
        if hit:
            return hit
    return default


def _spread(
    total: Decimal, counter_lines: list[tuple[str, Decimal]]
) -> list[tuple[str, Decimal]]:
    """Chia ``total`` cho các dòng đối ứng theo tỷ lệ số tiền của chúng.

    Trần chia là tổng bên đối ứng: phần tiền không có đối ứng ngoài nhóm tiền
    (rút TGNH nhập quỹ) bị bỏ qua, nhờ đó [50] luôn khớp chênh lệch tồn quỹ
    trong kỳ. Phần dư do làm tròn dồn vào dòng cuối để tổng chia ra khớp đúng
    số đã chia.
    """
    basis = sum((amount for _code, amount in counter_lines), _ZERO)
    if total <= _ZERO or basis <= _ZERO:
        return []
    payload = min(total, basis)
    shares: list[tuple[str, Decimal]] = []
    allocated = _ZERO
    for code, amount in counter_lines[:-1]:
        share = (payload * amount / basis).quantize(Decimal("1"))
        shares.append((code, share))
        allocated += share
    shares.append((counter_lines[-1][0], payload - allocated))
    return shares