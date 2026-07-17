"""CompanyService: đọc/ghi thông tin người nộp thuế trong bảng ``settings``.

Thuần CRUD trên key/value — không đụng tới bất kỳ logic kế toán/thuế nào.
"""
from __future__ import annotations

from data.repositories.settings_repo import SettingsRepository
from domain.models.company import CompanyProfile

_NAME_KEY = "company_name"
_TAX_CODE_KEY = "company_tax_code"
_ADDRESS_KEY = "company_address"


class CompanyService:
    def __init__(self, settings: SettingsRepository | None = None) -> None:
        self._settings = settings or SettingsRepository()

    def load(self) -> CompanyProfile:
        return CompanyProfile(
            name=self._settings.get(_NAME_KEY),
            tax_code=self._settings.get(_TAX_CODE_KEY),
            address=self._settings.get(_ADDRESS_KEY),
        )

    def save(self, profile: CompanyProfile) -> None:
        self._settings.set(_NAME_KEY, profile.name.strip())
        self._settings.set(_TAX_CODE_KEY, profile.tax_code.strip())
        self._settings.set(_ADDRESS_KEY, profile.address.strip())
