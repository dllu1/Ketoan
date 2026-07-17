"""Cash & bank module: build phiếu thu/chi as journal vouchers, derive movements."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from data.repositories.account_repo import AccountRepository
from domain.models.cash import CASH_ACCOUNTS, CashKind, CashMovement
from domain.models.journal import EntryStatus, JournalEntry, JournalLine
from domain.services.journal_service import JournalService


class CashValidationError(ValueError):
    pass


class CashService:
    def __init__(
        self,
        journal: JournalService,
        account_repo: AccountRepository | None = None,
    ) -> None:
        self._journal = journal
        self._accounts = account_repo or AccountRepository()

    # ----- queries ---------------------------------------------------------

    def balance(self, cash_account: str) -> Decimal:
        total = Decimal("0")
        for entry in self._journal.list_all():
            for line in entry.lines:
                if line.account_code == cash_account:
                    total += line.debit - line.credit
        return total

    def list_movements(self, cash_account: str | None = None) -> list[CashMovement]:
        """Every journal line touching a cash account, newest first, with a
        running per-account balance."""
        entries = sorted(
            self._journal.list_all(), key=lambda e: (e.entry_date, e.id or 0)
        )
        running: dict[str, Decimal] = {code: Decimal("0") for code in CASH_ACCOUNTS}
        movements: list[CashMovement] = []
        for entry in entries:
            for line in entry.lines:
                if line.account_code not in CASH_ACCOUNTS:
                    continue
                running[line.account_code] += line.debit - line.credit
                if cash_account and line.account_code != cash_account:
                    continue
                movements.append(
                    CashMovement(
                        entry_date=entry.entry_date,
                        ref=entry.ref,
                        description=line.description or entry.description,
                        cash_account=line.account_code,
                        counter_account=self._counter_account(entry, line.account_code),
                        inflow=line.debit,
                        outflow=line.credit,
                        balance=running[line.account_code],
                    )
                )
        movements.reverse()
        return movements

    # ----- commands --------------------------------------------------------

    def create_voucher(
        self,
        *,
        kind: CashKind,
        ref: str,
        cash_account: str,
        counter_account: str,
        amount: Decimal,
        entry_date: date | None = None,
        description: str = "",
        partner_code: str = "",
    ) -> JournalEntry:
        if not ref.strip():
            raise CashValidationError("Số phiếu là bắt buộc.")
        if cash_account not in CASH_ACCOUNTS:
            raise CashValidationError("Tài khoản quỹ phải là 111 hoặc 112.")
        if not counter_account.strip():
            raise CashValidationError("Tài khoản đối ứng là bắt buộc.")
        if amount <= 0:
            raise CashValidationError("Số tiền phải lớn hơn 0.")

        cash_line = self._line(cash_account)
        counter_line = self._line(counter_account)
        counter_line.partner_code = partner_code.strip()
        if kind is CashKind.RECEIPT:
            cash_line.debit = amount
            counter_line.credit = amount
        else:
            counter_line.debit = amount
            cash_line.credit = amount

        entry = JournalEntry(
            ref=ref.strip(),
            entry_date=entry_date or date.today(),
            description=description.strip(),
            status=EntryStatus.POSTED,
            lines=[cash_line, counter_line],
        )
        return self._journal.create(entry)

    def delete_voucher(self, ref: str) -> None:
        self._journal.delete_by_ref(ref)

    # ----- helpers ----------------------------------------------------------

    def _line(self, code: str) -> JournalLine:
        account = self._accounts.find_by_code(code)
        name = account.name if account else CASH_ACCOUNTS.get(code, "")
        return JournalLine(account_code=code, account_name=name)

    @staticmethod
    def _counter_account(entry: JournalEntry, cash_code: str) -> str:
        others = [ln.account_code for ln in entry.lines if ln.account_code != cash_code]
        if not others:
            return ""
        unique = list(dict.fromkeys(others))
        return unique[0] if len(unique) == 1 else "Nhiều TK"
