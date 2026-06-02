"""Business rules for the chart of accounts + circular (chế độ kế toán) switching."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from data.account_sets import available_circulars, load_accounts
from data.repositories.account_repo import AccountRepository
from data.repositories.settings_repo import SettingsRepository
from domain.models.account import Account

_ACTIVE_CIRCULAR_KEY = "active_circular"
_DEFAULT_CIRCULAR = "TT133"


@dataclass(frozen=True)
class CircularSwitchResult:
    """Outcome of :meth:`AccountService.set_circular`."""
    circular: str
    added: int
    conflicts: list[tuple[str, str, str]]   # (code, existing_name, template_name)


class AccountValidationError(ValueError):
    pass


class AccountService:
    def __init__(
        self,
        repo: AccountRepository,
        settings: SettingsRepository | None = None,
    ) -> None:
        self._repo = repo
        self._settings = settings or SettingsRepository()

    def list_all(self) -> list[Account]:
        return self._repo.list_all()

    def search(self, query: str) -> list[Account]:
        return self._repo.search(query.strip())

    def create(self, account: Account) -> Account:
        self._validate(account)
        if self._repo.find_by_code(account.code):
            raise AccountValidationError(f"Mã '{account.code}' đã tồn tại.")
        if not account.circular:
            account.circular = "CUSTOM"
        account.created_at = datetime.now()
        account.updated_at = account.created_at
        return self._repo.insert(account)

    def update(self, account: Account) -> Account:
        if account.id is None:
            raise AccountValidationError("Không thể cập nhật tài khoản chưa được lưu.")
        self._validate(account)
        account.updated_at = datetime.now()
        return self._repo.update(account)

    def deactivate(self, account_id: int) -> None:
        self._repo.set_active(account_id, False)

    # ----- circular configuration ------------------------------------------

    @staticmethod
    def available_circulars() -> list[tuple[str, str]]:
        return available_circulars()

    def active_circular(self) -> str:
        return self._settings.get(_ACTIVE_CIRCULAR_KEY, _DEFAULT_CIRCULAR)

    def ensure_seeded(self) -> None:
        """Populate the chart of accounts from the active circular if empty."""
        if not self._repo.list_all():
            self._load_template(self.active_circular())

    def set_circular(self, circular: str) -> CircularSwitchResult:
        """Switch the active circular, additively loading its accounts.

        Existing accounts are never deleted or renamed; this only inserts
        accounts the new circular introduces. Codes that already exist but
        carry a different name in the new template are reported as conflicts
        for the user to reconcile manually.
        """
        valid = {code for code, _ in available_circulars()}
        if circular not in valid:
            raise AccountValidationError(f"Không hỗ trợ thông tư '{circular}'.")
        added, conflicts = self._load_template(circular)
        self._settings.set(_ACTIVE_CIRCULAR_KEY, circular)
        return CircularSwitchResult(circular=circular, added=added, conflicts=conflicts)

    def _load_template(self, circular: str) -> tuple[int, list[tuple[str, str, str]]]:
        added = 0
        conflicts: list[tuple[str, str, str]] = []
        for entry in load_accounts(circular):
            existing = self._repo.find_by_code(entry["code"])
            if existing is None:
                self.create(
                    Account(
                        code=entry["code"],
                        name=entry["name"],
                        kind=entry.get("kind", ""),
                        circular=circular,
                    )
                )
                added += 1
            elif existing.name != entry["name"]:
                conflicts.append((entry["code"], existing.name, entry["name"]))
        return added, conflicts

    @staticmethod
    def _validate(account: Account) -> None:
        if not account.code.strip():
            raise AccountValidationError("Mã tài khoản là bắt buộc.")
        if not account.name.strip():
            raise AccountValidationError("Tên tài khoản là bắt buộc.")
