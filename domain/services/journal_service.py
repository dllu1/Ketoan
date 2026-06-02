"""Business rules for the General Journal (balanced Nợ = Có double-entry)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from data.repositories.journal_repo import JournalRepository
from domain.models.journal import EntryStatus, JournalEntry


class JournalValidationError(ValueError):
    pass


class JournalService:
    def __init__(self, repo: JournalRepository) -> None:
        self._repo = repo

    def list_all(self) -> list[JournalEntry]:
        return self._repo.list_all()

    def search(self, query: str) -> list[JournalEntry]:
        return self._repo.search(query.strip())

    def create(self, entry: JournalEntry) -> JournalEntry:
        self._validate(entry)
        if self._repo.find_by_ref(entry.ref):
            raise JournalValidationError(f"Số chứng từ '{entry.ref}' đã tồn tại.")
        entry.created_at = datetime.now()
        entry.updated_at = entry.created_at
        return self._repo.insert(entry)

    def update(self, entry: JournalEntry) -> JournalEntry:
        if entry.id is None:
            raise JournalValidationError("Không thể cập nhật bút toán chưa được lưu.")
        self._validate(entry)
        entry.updated_at = datetime.now()
        return self._repo.update(entry)

    def delete(self, entry_id: int) -> None:
        entry = self._find(entry_id)
        if entry is None:
            raise JournalValidationError("Không tìm thấy bút toán.")
        if entry.status is EntryStatus.POSTED:
            raise JournalValidationError(
                "Bút toán đã ghi sổ không thể xóa — hãy tạo bút toán đảo ngược."
            )
        self._repo.delete(entry_id)

    def _find(self, entry_id: int) -> JournalEntry | None:
        for entry in self._repo.list_all():
            if entry.id == entry_id:
                return entry
        return None

    @staticmethod
    def _validate(entry: JournalEntry) -> None:
        if not entry.ref.strip():
            raise JournalValidationError("Số chứng từ là bắt buộc.")
        if not entry.lines:
            raise JournalValidationError("Bút toán phải có ít nhất một dòng.")
        for line in entry.lines:
            if not line.account_code.strip():
                raise JournalValidationError("Mỗi dòng phải có tài khoản.")
            if line.debit < 0 or line.credit < 0:
                raise JournalValidationError("Số tiền Nợ/Có không được âm.")
            one_sided = (line.debit > 0) != (line.credit > 0)
            if not one_sided:
                raise JournalValidationError(
                    f"Dòng TK {line.account_code}: mỗi dòng chỉ ghi Nợ hoặc Có."
                )
        if entry.status is EntryStatus.POSTED and not entry.is_balanced:
            raise JournalValidationError(
                "Bút toán chưa cân đối: Tổng Nợ phải bằng Tổng Có."
            )
