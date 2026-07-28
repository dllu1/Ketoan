"""Phân bổ chi phí trả trước (TK 242 / 1421 / 1422) theo tháng.

Sổ tay "Nhập liệu" mục I.3.d. Mỗi tháng ghi ``Nợ TK chi phí / Có 242`` cho phần
phân bổ của tháng đó; số chứng từ ``PBCP-YYYYMM`` nên chạy lại một tháng sẽ thay
thế bút toán cũ thay vì cộng dồn (giống khấu hao TSCĐ ``KH-YYYYMM``).
"""
from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

from data.repositories.account_repo import AccountRepository
from data.repositories.prepaid_repo import PrepaidRepository
from domain.models.journal import EntryStatus, JournalEntry, JournalLine
from domain.models.prepaid import PrepaidExpense, PrepaidScheduleRow

_ZERO = Decimal("0")


class PrepaidValidationError(ValueError):
    pass


class PrepaidService:
    def __init__(
        self,
        repo: PrepaidRepository | None = None,
        journal=None,
        accounts: AccountRepository | None = None,
    ) -> None:
        self._repo = repo or PrepaidRepository()
        self._journal = journal
        self._accounts = accounts

    # ----- CRUD -----------------------------------------------------------

    def list_all(self) -> list[PrepaidExpense]:
        return self._repo.list_all()

    def save(self, prepaid: PrepaidExpense) -> PrepaidExpense:
        self._validate(prepaid)
        existing = self._repo.find_by_code(prepaid.code)
        if prepaid.id is None and existing is not None:
            raise PrepaidValidationError(
                f"Mã chi phí trả trước '{prepaid.code}' đã tồn tại."
            )
        if prepaid.id is None:
            return self._repo.insert(prepaid)
        return self._repo.update(prepaid)

    def delete(self, prepaid_id: int) -> None:
        self._repo.delete(prepaid_id)

    @staticmethod
    def _validate(p: PrepaidExpense) -> None:
        if not p.code.strip():
            raise PrepaidValidationError("Mã chi phí trả trước là bắt buộc.")
        if p.total_amount <= _ZERO:
            raise PrepaidValidationError("Số tiền phân bổ phải lớn hơn 0.")
        if p.months <= 0:
            raise PrepaidValidationError("Số tháng phân bổ phải lớn hơn 0.")
        if not 1 <= p.start_month <= 12:
            raise PrepaidValidationError("Tháng bắt đầu phải từ 1 đến 12.")
        if not p.expense_account.strip():
            raise PrepaidValidationError("Phải chọn tài khoản chi phí nhận phân bổ.")

    # ----- lịch phân bổ ---------------------------------------------------

    def schedule(self, prepaid: PrepaidExpense) -> list[PrepaidScheduleRow]:
        """Toàn bộ lịch phân bổ của một khoản (mỗi tháng một dòng)."""
        rows: list[PrepaidScheduleRow] = []
        for offset in range(prepaid.months):
            year = prepaid.start_year + (prepaid.start_month - 1 + offset) // 12
            month = (prepaid.start_month - 1 + offset) % 12 + 1
            rows.append(PrepaidScheduleRow(
                year=year,
                month=month,
                amount=prepaid.amount_for(year, month),
                allocated=prepaid.allocated_through(year, month),
                remaining=prepaid.remaining_after(year, month),
            ))
        return rows

    def monthly_total(self, year: int, month: int) -> Decimal:
        """Tổng phân bổ của tất cả các khoản trong một tháng."""
        return sum(
            (p.amount_for(year, month) for p in self._repo.list_all()), _ZERO
        )

    def due_in(self, year: int, month: int) -> list[PrepaidExpense]:
        """Các khoản có phát sinh phân bổ trong tháng."""
        return [
            p for p in self._repo.list_all() if p.amount_for(year, month) > _ZERO
        ]

    # ----- ghi sổ ---------------------------------------------------------

    def post_monthly(self, year: int, month: int) -> JournalEntry | None:
        """Bút toán phân bổ tháng: Nợ TK chi phí / Có 242.

        Idempotent theo ``PBCP-YYYYMM``; trả về ``None`` nếu tháng không có
        khoản nào tới hạn phân bổ.
        """
        if self._journal is None:
            raise PrepaidValidationError(
                "Chưa cấu hình sổ nhật ký để ghi phân bổ chi phí trả trước."
            )
        ref = f"PBCP-{year}{month:02d}"
        self._journal.delete_by_ref(ref)

        debit_by_account: dict[str, Decimal] = {}
        credit_by_account: dict[str, Decimal] = {}
        for prepaid in self._repo.list_all():
            amount = prepaid.amount_for(year, month)
            if amount <= _ZERO:
                continue
            debit_by_account[prepaid.expense_account] = (
                debit_by_account.get(prepaid.expense_account, _ZERO) + amount
            )
            credit_by_account[prepaid.asset_account] = (
                credit_by_account.get(prepaid.asset_account, _ZERO) + amount
            )
        if not debit_by_account:
            return None

        names = self._account_names
        lines = [
            JournalLine(account_code=code, account_name=names.get(code, ""),
                        description="Phân bổ chi phí trả trước", debit=value)
            for code, value in sorted(debit_by_account.items())
        ] + [
            JournalLine(account_code=code, account_name=names.get(code, ""),
                        description="Phân bổ chi phí trả trước", credit=value)
            for code, value in sorted(credit_by_account.items())
        ]
        return self._journal.create(JournalEntry(
            ref=ref,
            entry_date=_last_day(year, month),
            description=f"Phân bổ chi phí trả trước tháng {month:02d}/{year}",
            status=EntryStatus.POSTED,
            lines=lines,
        ))

    @property
    def _account_names(self) -> dict[str, str]:
        repo = self._accounts or AccountRepository()
        return {a.code: a.name for a in repo.list_all()}


def _last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])
