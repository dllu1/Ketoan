"""Business rules for partner directory."""
from __future__ import annotations

import re
from datetime import datetime

from data.repositories.partner_repo import PartnerRepository
from domain.models.partner import Partner, PartnerType

_TAX_CODE_RE = re.compile(r"^\d{10}(-\d{3})?$")


class PartnerValidationError(ValueError):
    pass


class PartnerService:
    def __init__(self, repo: PartnerRepository) -> None:
        self._repo = repo

    def list_all(self, type_filter: PartnerType | None = None) -> list[Partner]:
        return self._repo.list_all(type_filter)

    def search(self, query: str) -> list[Partner]:
        return self._repo.search(query.strip())

    def create(self, partner: Partner) -> Partner:
        self._validate(partner)
        if self._repo.find_by_code(partner.code):
            raise PartnerValidationError(f"Mã '{partner.code}' đã tồn tại.")
        partner.created_at = datetime.now()
        partner.updated_at = partner.created_at
        return self._repo.insert(partner)

    def update(self, partner: Partner) -> Partner:
        if partner.id is None:
            raise PartnerValidationError("Không thể cập nhật đối tác chưa được lưu.")
        self._validate(partner)
        partner.updated_at = datetime.now()
        return self._repo.update(partner)

    def deactivate(self, partner_id: int) -> None:
        self._repo.set_active(partner_id, False)

    @staticmethod
    def _validate(partner: Partner) -> None:
        if not partner.code.strip():
            raise PartnerValidationError("Mã đối tác là bắt buộc.")
        if not partner.name.strip():
            raise PartnerValidationError("Tên đối tác là bắt buộc.")
        if partner.tax_code and not _TAX_CODE_RE.match(partner.tax_code):
            raise PartnerValidationError(
                "Mã số thuế không hợp lệ (định dạng: 10 số hoặc 10-3 số)."
            )
