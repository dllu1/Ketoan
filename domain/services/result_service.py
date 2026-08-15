"""Kết chuyển cuối kỳ để xác định kết quả kinh doanh (TK 911).

Theo sổ tay kế toán Hưng Phát (mục V + phần "Nhập liệu"): cuối kỳ kết chuyển
doanh thu và chi phí sang TK 911, rồi đưa chênh lệch sang TK 4212 (lợi nhuận
năm nay).

**Không còn danh sách tài khoản cứng.** Mỗi tài khoản được kết chuyển đi đâu và
theo chiều nào do bảng quy tắc (:mod:`domain.services.transfer_rule_service`)
quyết định — người dùng sửa trong màn hình *Kết chuyển*. Bộ mặc định tái lập
đúng cách làm cũ, nên sổ sách hiện có không đổi cho tới khi người dùng chỉnh.

Bút toán sinh ra:

* ``KC-GV/<kỳ>``   Nợ 632 / Có 155,156 …  (điều chỉnh giá vốn cuối kỳ)
* ``<nhóm>/<kỳ>``  một bút toán cho mỗi nhóm quy tắc (mặc định KC-DT, KC-CP)
* ``KC-LN/<kỳ>``   Nợ 911 / Có 4212 (lãi)  —  Nợ 4212 / Có 911 (lỗ)

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
from domain.models.transfer_rule import TransferDirection, TransferRule
from domain.services.cogs_service import CogsService
from domain.services.journal_service import JournalService
from domain.services.period_tag import period_tag as _period_tag
from domain.services.transfer_rule_service import (
    DEFAULT_PROFIT_ACCOUNT,
    DEFAULT_RESULT_ACCOUNT,
    RESULT_GROUP_REF,
    TransferRuleService,
)

_ZERO = Decimal("0")

RESULT_ACCOUNT = DEFAULT_RESULT_ACCOUNT     # Xác định kết quả kinh doanh
PROFIT_ACCOUNT = DEFAULT_PROFIT_ACCOUNT     # Lợi nhuận sau thuế chưa phân phối

# Số chứng từ của bộ quy tắc mặc định — vẫn phải dọn được kể cả sau khi người
# dùng đổi tên nhóm, nếu không bút toán cũ sẽ nằm lại trong sổ mãi mãi.
_LEGACY_PREFIXES = ("KC-DT", "KC-CP", RESULT_GROUP_REF)


class ResultError(ValueError):
    pass


@dataclass
class TransferLine:
    """Một tài khoản được kết chuyển và số tiền của nó."""

    account_code: str
    account_name: str = ""
    amount: Decimal = _ZERO
    target_account: str = RESULT_ACCOUNT
    direction: TransferDirection = TransferDirection.DEBIT_SOURCE
    group_ref: str = "KC-DT"
    sort_order: int = 0


@dataclass
class TransferGroup:
    """Các dòng cùng đi vào một bút toán (một số chứng từ)."""

    ref_prefix: str
    lines: list[TransferLine] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return sum((ln.amount for ln in self.lines), _ZERO)

    @property
    def sort_order(self) -> int:
        return min((ln.sort_order for ln in self.lines), default=0)


@dataclass
class ResultPlan:
    """Bản xem trước của một lượt kết chuyển (chưa ghi sổ)."""

    period_tag: str
    date_from: date
    date_to: date
    lines: list[TransferLine] = field(default_factory=list)
    result_account: str = RESULT_ACCOUNT
    profit_account: str = PROFIT_ACCOUNT

    # ----- gom nhóm --------------------------------------------------------

    @property
    def groups(self) -> list[TransferGroup]:
        grouped: dict[str, TransferGroup] = {}
        for line in self.lines:
            group = grouped.get(line.group_ref)
            if group is None:
                group = TransferGroup(ref_prefix=line.group_ref)
                grouped[line.group_ref] = group
            group.lines.append(line)
        return sorted(grouped.values(), key=lambda g: (g.sort_order, g.ref_prefix))

    # ----- các lát cắt quen thuộc (doanh thu / chi phí) --------------------

    @property
    def revenue(self) -> list[TransferLine]:
        """Dòng ghi Nợ nguồn / Có TK kết quả — doanh thu, thu nhập."""
        return [
            ln for ln in self.lines
            if ln.direction is TransferDirection.DEBIT_SOURCE
            and ln.target_account == self.result_account
        ]

    @property
    def expense(self) -> list[TransferLine]:
        """Dòng ghi Có nguồn / Nợ TK kết quả — chi phí, giá vốn."""
        return [
            ln for ln in self.lines
            if ln.direction is TransferDirection.CREDIT_SOURCE
            and ln.target_account == self.result_account
        ]

    @property
    def total_revenue(self) -> Decimal:
        return sum((ln.amount for ln in self.revenue), _ZERO)

    @property
    def total_expense(self) -> Decimal:
        return sum((ln.amount for ln in self.expense), _ZERO)

    @property
    def profit(self) -> Decimal:
        """Lãi (>0) hoặc lỗ (<0) — số dư TK kết quả sau khi chạy hết quy tắc."""
        return self.total_revenue - self.total_expense

    @property
    def is_profit(self) -> bool:
        return self.profit >= _ZERO

    @property
    def is_empty(self) -> bool:
        return not self.lines


class ResultService:
    def __init__(
        self,
        journal: JournalService,
        accounts: AccountRepository | None = None,
        cogs: CogsService | None = None,
        rules: TransferRuleService | None = None,
    ) -> None:
        self._journal = journal
        self._accounts = accounts
        self._cogs = cogs or CogsService(journal, accounts=accounts)
        self._rules = rules or TransferRuleService()

    @property
    def _account_names(self) -> dict[str, str]:
        repo = self._accounts or AccountRepository()
        return {a.code: a.name for a in repo.list_all()}

    # ----- cấu hình --------------------------------------------------------

    def rules(self) -> list[TransferRule]:
        return self._rules.list_rules(active_only=True)

    def result_account(self) -> str:
        return self._rules.result_account()

    def profit_account(self) -> str:
        return self._rules.profit_account()

    def _ref_prefixes(self, rules: list[TransferRule] | None = None) -> list[str]:
        """Mọi tiền tố số chứng từ mà lượt kết chuyển này sở hữu.

        Gồm cả nhóm mặc định cũ để bút toán sinh trước khi người dùng đổi tên
        nhóm vẫn được dọn khi kết chuyển lại. Cố ý **không** có ``KC-GV``: giá
        vốn do :class:`CogsService` tự quản lý và phải đọc được khi gom chi phí.
        """
        prefixes = {r.group_ref.strip() for r in (rules if rules is not None
                                                  else self.rules())}
        prefixes.update(_LEGACY_PREFIXES)
        return sorted(p for p in prefixes if p)

    # ----- xem trước -----------------------------------------------------

    def plan(self, date_from: date, date_to: date) -> ResultPlan:
        """Gom số phát sinh trong kỳ theo bảng quy tắc kết chuyển.

        Bỏ qua chính các bút toán kết chuyển để chạy lại không bị cộng dồn, và
        bỏ qua bút toán nháp.
        """
        rules = self.rules()
        names = self._account_names
        prefixes = tuple(f"{p}/" for p in self._ref_prefixes(rules))
        result_account = self.result_account()

        # mã TK → [PS Nợ, PS Có]; chỉ giữ TK có quy tắc áp dụng.
        movements: dict[str, list[Decimal]] = {}
        applied: dict[str, TransferRule] = {}
        for entry in self._journal.list_all():
            if entry.status is not EntryStatus.POSTED:
                continue
            if not (date_from <= entry.entry_date <= date_to):
                continue
            if entry.ref.startswith(prefixes):
                continue
            for line in entry.lines:
                code = line.account_code.strip()
                if code == result_account:
                    continue
                rule = applied.get(code)
                if rule is None:
                    rule = TransferRuleService.rule_for(rules, code)
                    if rule is None:
                        continue
                    applied[code] = rule
                    movements[code] = [_ZERO, _ZERO]
                movements[code][0] += line.debit
                movements[code][1] += line.credit

        lines: list[TransferLine] = []
        for code, (debit, credit) in movements.items():
            rule = applied[code]
            amount = rule.signed_amount(debit, credit)
            if amount == _ZERO:
                continue
            direction = rule.direction
            if amount < _ZERO:
                # Số dư ngược chiều khai báo (vd: TK doanh thu dư Nợ vì hàng bán
                # trả lại lớn hơn doanh thu) — đảo bút toán thay vì ghi số âm.
                direction = direction.flipped
                amount = -amount
            lines.append(TransferLine(
                account_code=code,
                account_name=names.get(code, rule.label),
                amount=amount,
                target_account=rule.target_account.strip(),
                direction=direction,
                group_ref=rule.group_ref.strip(),
                sort_order=rule.sort_order,
            ))
        lines.sort(key=lambda ln: (ln.sort_order, ln.account_code))

        return ResultPlan(
            period_tag=_period_tag(date_from, date_to),
            date_from=date_from,
            date_to=date_to,
            lines=lines,
            result_account=result_account,
            profit_account=self.profit_account(),
        )

    # ----- ghi sổ --------------------------------------------------------

    def is_posted(self, date_from: date, date_to: date) -> bool:
        tag = _period_tag(date_from, date_to)
        return self._cogs.is_posted(date_from, date_to) or any(
            self._journal.find_by_ref(f"{prefix}/{tag}") is not None
            for prefix in self._ref_prefixes()
        )

    def unpost(self, date_from: date, date_to: date) -> None:
        """Xóa các bút toán kết chuyển của kỳ (kể cả giá vốn KC-GV)."""
        tag = _period_tag(date_from, date_to)
        for prefix in self._ref_prefixes():
            self._journal.delete_by_ref(f"{prefix}/{tag}")
        self._cogs.unpost(date_from, date_to)

    def post(self, date_from: date, date_to: date) -> list[JournalEntry]:
        """Chạy hết bảng quy tắc, rồi đưa số dư TK kết quả sang TK lợi nhuận."""
        if date_from > date_to:
            raise ResultError("Khoảng thời gian kết chuyển không hợp lệ.")
        # Xóa trước để vừa idempotent vừa không tự tính lại chính mình.
        self.unpost(date_from, date_to)
        # Giá vốn phải kết chuyển TRƯỚC khi gom chi phí: KC-GV mới sinh ra phần
        # 632 còn thiếu mà quy tắc chi phí dưới đây đưa sang TK kết quả. (KC-GV
        # cố ý không nằm trong _ref_prefixes nên plan() vẫn đọc được 632 của nó.)
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

        for group in plan.groups:
            created.append(self._journal.create(
                self._group_entry(group, names, tag, date_to)
            ))

        profit_entry = self._profit_entry(plan, names, tag, date_to)
        if profit_entry is not None:
            created.append(self._journal.create(profit_entry))
        return created

    # ----- dựng bút toán ---------------------------------------------------

    def _group_entry(
        self,
        group: TransferGroup,
        names: dict[str, str],
        tag: str,
        entry_date: date,
    ) -> JournalEntry:
        """Một bút toán cho cả nhóm: dòng nguồn chi tiết, dòng đích gộp lại."""
        description = _group_description(group)
        targets_label = ", ".join(sorted({ln.target_account for ln in group.lines}))
        lines: list[JournalLine] = []
        # (mã TK đích, ghi Nợ?) → số tiền gộp
        targets: dict[tuple[str, bool], Decimal] = {}
        for line in group.lines:
            source_debit = line.direction is TransferDirection.DEBIT_SOURCE
            lines.append(JournalLine(
                account_code=line.account_code,
                account_name=line.account_name or names.get(line.account_code, ""),
                description=description,
                debit=line.amount if source_debit else _ZERO,
                credit=_ZERO if source_debit else line.amount,
            ))
            key = (line.target_account, not source_debit)
            targets[key] = targets.get(key, _ZERO) + line.amount

        for (code, target_debit), amount in sorted(targets.items()):
            lines.append(JournalLine(
                account_code=code,
                account_name=names.get(code, ""),
                description=description,
                debit=amount if target_debit else _ZERO,
                credit=_ZERO if target_debit else amount,
            ))
        return JournalEntry(
            ref=f"{group.ref_prefix}/{tag}",
            entry_date=entry_date,
            description=f"{description} {tag} sang TK {targets_label}",
            status=EntryStatus.POSTED,
            lines=lines,
        )

    def _profit_entry(
        self,
        plan: ResultPlan,
        names: dict[str, str],
        tag: str,
        entry_date: date,
    ) -> JournalEntry | None:
        """Đưa số dư TK kết quả sang TK lợi nhuận. ``None`` khi hòa vốn."""
        profit = plan.profit
        if profit == _ZERO:
            return None
        amount = abs(profit)
        result_line = JournalLine(
            account_code=plan.result_account,
            account_name=names.get(plan.result_account, ""),
            description="Kết chuyển kết quả kinh doanh",
        )
        profit_line = JournalLine(
            account_code=plan.profit_account,
            account_name=names.get(plan.profit_account, ""),
            description="Kết chuyển kết quả kinh doanh",
        )
        # Lãi: Nợ 911 / Có 4212. Lỗ: đảo lại.
        if profit > _ZERO:
            result_line.debit = amount
            profit_line.credit = amount
        else:
            profit_line.debit = amount
            result_line.credit = amount
        return JournalEntry(
            ref=f"{RESULT_GROUP_REF}/{tag}",
            entry_date=entry_date,
            description=(
                f"Kết chuyển {'lãi' if profit > _ZERO else 'lỗ'} {tag} sang TK "
                f"{plan.profit_account}"
            ),
            status=EntryStatus.POSTED,
            lines=[result_line, profit_line],
        )


# ----- helpers -------------------------------------------------------------


def _group_description(group: TransferGroup) -> str:
    """Diễn giải bút toán suy từ chiều kết chuyển của nhóm.

    Nhóm toàn dòng ghi Nợ nguồn là kết chuyển doanh thu, toàn ghi Có nguồn là
    kết chuyển chi phí; nhóm trộn cả hai thì gọi chung.
    """
    directions = {ln.direction for ln in group.lines}
    if directions == {TransferDirection.DEBIT_SOURCE}:
        return "Kết chuyển doanh thu"
    if directions == {TransferDirection.CREDIT_SOURCE}:
        return "Kết chuyển chi phí"
    return "Kết chuyển"
