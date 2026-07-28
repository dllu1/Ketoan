"""Kết chuyển cuối kỳ để xác định kết quả kinh doanh (TK 911).

Theo sổ tay kế toán Hưng Phát (mục V + phần "Nhập liệu"): cuối kỳ kết chuyển
doanh thu và chi phí sang TK 911, rồi đưa chênh lệch sang TK 4212 (lợi nhuận
năm nay).

Sinh **ba** bút toán riêng cho dễ đối chiếu, mỗi bút toán tự cân đối:

* ``KC-GV/<kỳ>``  Nợ 632                       / Có 155/156 …  (kết chuyển giá vốn)
* ``KC-DT/<kỳ>``  Nợ 511/515/711 …            / Có 911     (kết chuyển doanh thu)
* ``KC-CP/<kỳ>``  Nợ 911                       / Có 632/641/642/811/821 …
* ``KC-LN/<kỳ>``  Nợ 911 / Có 4212 (lãi)  —  Nợ 4212 / Có 911 (lỗ)

Idempotent: :meth:`post` xóa các bút toán kết chuyển cũ của kỳ rồi tạo lại, nên
chạy nhiều lần không cộng dồn. Số dư dùng để kết chuyển **không tính** chính các
bút toán kết chuyển (chúng đã bị xóa trước khi tính).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from data.repositories.account_repo import AccountRepository
from domain.models.journal import EntryStatus, JournalEntry, JournalLine
from domain.services.cogs_service import CogsService
from domain.services.journal_service import JournalService
from domain.services.period_tag import period_tag as _period_tag

_ZERO = Decimal("0")

# Doanh thu / thu nhập — số dư Có, kết chuyển bằng bút toán Nợ TK / Có 911.
_REVENUE_ACCOUNTS = ("511", "512", "515", "711")
# Chi phí — số dư Nợ, kết chuyển bằng bút toán Nợ 911 / Có TK.
# 631 (giá thành SX) cố ý KHÔNG có: nó kết chuyển sang 632, không thẳng vào 911.
_EXPENSE_ACCOUNTS = ("632", "635", "641", "642", "811", "812", "821")

RESULT_ACCOUNT = "911"      # Xác định kết quả kinh doanh
PROFIT_ACCOUNT = "4212"     # Lợi nhuận sau thuế chưa phân phối — năm nay

# Tiền tố số chứng từ của ba bút toán kết chuyển.
_REF_REVENUE = "KC-DT"
_REF_EXPENSE = "KC-CP"
_REF_RESULT = "KC-LN"
_REF_PREFIXES = (_REF_REVENUE, _REF_EXPENSE, _REF_RESULT)


class ResultError(ValueError):
    pass


@dataclass
class TransferLine:
    """Một tài khoản được kết chuyển và số tiền của nó."""

    account_code: str
    account_name: str = ""
    amount: Decimal = _ZERO


@dataclass
class ResultPlan:
    """Bản xem trước của một lượt kết chuyển (chưa ghi sổ)."""

    period_tag: str
    date_from: date
    date_to: date
    revenue: list[TransferLine] = field(default_factory=list)
    expense: list[TransferLine] = field(default_factory=list)

    @property
    def total_revenue(self) -> Decimal:
        return sum((ln.amount for ln in self.revenue), _ZERO)

    @property
    def total_expense(self) -> Decimal:
        return sum((ln.amount for ln in self.expense), _ZERO)

    @property
    def profit(self) -> Decimal:
        """Lãi (>0) hoặc lỗ (<0) trước khi đưa sang 4212."""
        return self.total_revenue - self.total_expense

    @property
    def is_profit(self) -> bool:
        return self.profit >= _ZERO

    @property
    def is_empty(self) -> bool:
        return not self.revenue and not self.expense


class ResultService:
    def __init__(
        self,
        journal: JournalService,
        accounts: AccountRepository | None = None,
        cogs: CogsService | None = None,
    ) -> None:
        self._journal = journal
        self._accounts = accounts
        self._cogs = cogs or CogsService(journal, accounts=accounts)

    @property
    def _account_names(self) -> dict[str, str]:
        repo = self._accounts or AccountRepository()
        return {a.code: a.name for a in repo.list_all()}

    # ----- xem trước -----------------------------------------------------

    def plan(self, date_from: date, date_to: date) -> ResultPlan:
        """Gom số phát sinh của các TK doanh thu / chi phí trong kỳ.

        Bỏ qua chính các bút toán kết chuyển (``KC-…``) để chạy lại không bị
        cộng dồn, và bỏ qua bút toán nháp.
        """
        names = self._account_names
        revenue: dict[str, Decimal] = {}
        expense: dict[str, Decimal] = {}
        for entry in self._journal.list_all():
            if entry.status is not EntryStatus.POSTED:
                continue
            if not (date_from <= entry.entry_date <= date_to):
                continue
            if _is_transfer_ref(entry.ref):
                continue
            for line in entry.lines:
                code = line.account_code.strip()
                if _matches(code, _REVENUE_ACCOUNTS):
                    # Doanh thu treo bên Có; hàng giảm trừ ghi Nợ nên trừ ra.
                    revenue[code] = revenue.get(code, _ZERO) + line.credit - line.debit
                elif _matches(code, _EXPENSE_ACCOUNTS):
                    expense[code] = expense.get(code, _ZERO) + line.debit - line.credit
        return ResultPlan(
            period_tag=_period_tag(date_from, date_to),
            date_from=date_from,
            date_to=date_to,
            revenue=_lines(revenue, names),
            expense=_lines(expense, names),
        )

    # ----- ghi sổ --------------------------------------------------------

    def is_posted(self, date_from: date, date_to: date) -> bool:
        tag = _period_tag(date_from, date_to)
        return self._cogs.is_posted(date_from, date_to) or any(
            self._journal.find_by_ref(f"{prefix}/{tag}") is not None
            for prefix in _REF_PREFIXES
        )

    def unpost(self, date_from: date, date_to: date) -> None:
        """Xóa các bút toán kết chuyển của kỳ (kể cả giá vốn KC-GV)."""
        tag = _period_tag(date_from, date_to)
        for prefix in _REF_PREFIXES:
            self._journal.delete_by_ref(f"{prefix}/{tag}")
        self._cogs.unpost(date_from, date_to)

    def post(self, date_from: date, date_to: date) -> list[JournalEntry]:
        """Kết chuyển doanh thu + chi phí sang 911, rồi 911 sang 4212."""
        if date_from > date_to:
            raise ResultError("Khoảng thời gian kết chuyển không hợp lệ.")
        # Xóa trước để vừa idempotent vừa không tự tính lại chính mình.
        self.unpost(date_from, date_to)
        # Giá vốn phải kết chuyển TRƯỚC khi gom chi phí: KC-GV mới sinh ra số dư
        # Nợ 632 mà KC-CP dưới đây đưa sang 911. (KC-GV cố ý không nằm trong
        # _REF_PREFIXES nên plan() vẫn đọc được 632 của nó.)
        created: list[JournalEntry] = []
        cogs_entry = self._cogs.post(date_from, date_to)
        if cogs_entry is not None:
            created.append(cogs_entry)
        plan = self.plan(date_from, date_to)
        if plan.is_empty:
            raise ResultError(
                "Kỳ này chưa có phát sinh doanh thu / chi phí nào để kết chuyển."
            )
        names = self._account_names
        tag = plan.period_tag

        if plan.revenue:
            created.append(self._journal.create(JournalEntry(
                ref=f"{_REF_REVENUE}/{tag}",
                entry_date=date_to,
                description=f"Kết chuyển doanh thu {tag} sang TK 911",
                status=EntryStatus.POSTED,
                lines=[
                    JournalLine(account_code=ln.account_code,
                                account_name=ln.account_name,
                                description="Kết chuyển doanh thu",
                                debit=ln.amount)
                    for ln in plan.revenue
                ] + [
                    JournalLine(account_code=RESULT_ACCOUNT,
                                account_name=names.get(RESULT_ACCOUNT, ""),
                                description="Kết chuyển doanh thu",
                                credit=plan.total_revenue)
                ],
            )))

        if plan.expense:
            created.append(self._journal.create(JournalEntry(
                ref=f"{_REF_EXPENSE}/{tag}",
                entry_date=date_to,
                description=f"Kết chuyển chi phí {tag} sang TK 911",
                status=EntryStatus.POSTED,
                lines=[
                    JournalLine(account_code=RESULT_ACCOUNT,
                                account_name=names.get(RESULT_ACCOUNT, ""),
                                description="Kết chuyển chi phí",
                                debit=plan.total_expense)
                ] + [
                    JournalLine(account_code=ln.account_code,
                                account_name=ln.account_name,
                                description="Kết chuyển chi phí",
                                credit=ln.amount)
                    for ln in plan.expense
                ],
            )))

        profit = plan.profit
        if profit != _ZERO:
            # Lãi: Nợ 911 / Có 4212. Lỗ: đảo lại.
            amount = abs(profit)
            result_line = JournalLine(
                account_code=RESULT_ACCOUNT,
                account_name=names.get(RESULT_ACCOUNT, ""),
                description="Kết chuyển kết quả kinh doanh",
            )
            profit_line = JournalLine(
                account_code=PROFIT_ACCOUNT,
                account_name=names.get(PROFIT_ACCOUNT, ""),
                description="Kết chuyển kết quả kinh doanh",
            )
            if profit > _ZERO:
                result_line.debit = amount
                profit_line.credit = amount
            else:
                profit_line.debit = amount
                result_line.credit = amount
            created.append(self._journal.create(JournalEntry(
                ref=f"{_REF_RESULT}/{tag}",
                entry_date=date_to,
                description=(
                    f"Kết chuyển {'lãi' if profit > _ZERO else 'lỗ'} {tag} sang TK 4212"
                ),
                status=EntryStatus.POSTED,
                lines=[result_line, profit_line],
            )))
        return created


# ----- helpers -------------------------------------------------------------


def _matches(code: str, prefixes: tuple[str, ...]) -> bool:
    """TK con vẫn thuộc nhóm cha (vd 5111 → 511, 6421 → 642)."""
    return any(code.startswith(p) for p in prefixes)


def _is_transfer_ref(ref: str) -> bool:
    return any(ref.startswith(f"{p}/") for p in _REF_PREFIXES)


def _lines(totals: dict[str, Decimal], names: dict[str, str]) -> list[TransferLine]:
    """Bỏ tài khoản có số dư 0; sắp theo mã cho ổn định."""
    return [
        TransferLine(account_code=code, account_name=names.get(code, ""), amount=amount)
        for code, amount in sorted(totals.items())
        if amount != _ZERO
    ]


