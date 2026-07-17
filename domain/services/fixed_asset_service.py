"""Fixed asset rules: straight-line depreciation + monthly posting to 214."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from data.repositories.account_repo import AccountRepository
from data.repositories.fixed_asset_repo import FixedAssetRepository
from domain.models.fixed_asset import FixedAsset
from domain.models.journal import EntryStatus, JournalEntry, JournalLine
from domain.services.journal_service import JournalService

_ACCUMULATED_DEPR_ACCOUNT = "214"
_DEPR_NAMES = {
    "214": "Hao mòn tài sản cố định",
    "627": "Chi phí sản xuất chung",
    "641": "Chi phí bán hàng",
    "642": "Chi phí quản lý doanh nghiệp",
}


@dataclass(frozen=True)
class DepreciationPeriod:
    month: int
    depreciation: Decimal
    accumulated: Decimal
    book_value: Decimal


class FixedAssetValidationError(ValueError):
    pass


class FixedAssetService:
    def __init__(
        self,
        repo: FixedAssetRepository,
        journal: JournalService | None = None,
        account_repo: AccountRepository | None = None,
    ) -> None:
        self._repo = repo
        self._journal = journal
        self._accounts = account_repo or AccountRepository()

    # ----- CRUD ------------------------------------------------------------

    def list_all(self) -> list[FixedAsset]:
        return self._repo.list_all()

    def search(self, query: str) -> list[FixedAsset]:
        return self._repo.search(query.strip())

    def create(self, asset: FixedAsset) -> FixedAsset:
        self._validate(asset)
        if self._repo.find_by_code(asset.code):
            raise FixedAssetValidationError(f"Mã '{asset.code}' đã tồn tại.")
        asset.created_at = datetime.now()
        asset.updated_at = asset.created_at
        return self._repo.insert(asset)

    def update(self, asset: FixedAsset) -> FixedAsset:
        if asset.id is None:
            raise FixedAssetValidationError("Không thể cập nhật tài sản chưa được lưu.")
        self._validate(asset)
        asset.updated_at = datetime.now()
        return self._repo.update(asset)

    def deactivate(self, asset_id: int) -> None:
        self._repo.set_active(asset_id, False)

    # ----- depreciation ----------------------------------------------------

    def depreciation_schedule(self, asset: FixedAsset, year: int) -> list[DepreciationPeriod]:
        """12 dòng khấu hao của một năm cho lưới khấu hao động."""
        schedule: list[DepreciationPeriod] = []
        for month in range(1, 13):
            schedule.append(
                DepreciationPeriod(
                    month=month,
                    depreciation=asset.depreciation_for(year, month),
                    accumulated=asset.accumulated_through(year, month),
                    book_value=asset.book_value_through(year, month),
                )
            )
        return schedule

    def post_monthly_depreciation(self, year: int, month: int) -> JournalEntry | None:
        """Ghi bút toán khấu hao tháng: Nợ chi phí / Có 214 cho mọi TSCĐ đang KH.

        Idempotent theo số chứng từ ``KH-YYYYMM``; trả về None nếu không có
        khấu hao trong kỳ."""
        if self._journal is None:
            raise FixedAssetValidationError("Chưa cấu hình sổ nhật ký để ghi khấu hao.")
        ref = f"KH-{year}{month:02d}"
        self._journal.delete_by_ref(ref)

        expense_by_account: dict[str, Decimal] = {}
        total = Decimal("0")
        for asset in self._repo.list_all():
            amount = asset.depreciation_for(year, month)
            if amount <= 0:
                continue
            expense_by_account[asset.expense_account] = (
                expense_by_account.get(asset.expense_account, Decimal("0")) + amount
            )
            total += amount
        if total <= 0:
            return None

        lines: list[JournalLine] = []
        for account, value in sorted(expense_by_account.items()):
            lines.append(self._line(account, debit=value))
        lines.append(self._line(_ACCUMULATED_DEPR_ACCOUNT, credit=total))

        return self._journal.create(
            JournalEntry(
                ref=ref,
                entry_date=_last_day(year, month),
                description=f"Khấu hao TSCĐ tháng {month:02d}/{year}",
                status=EntryStatus.POSTED,
                lines=lines,
            )
        )

    # ----- helpers ----------------------------------------------------------

    def _line(self, code: str, *, debit: Decimal = Decimal("0"), credit: Decimal = Decimal("0")) -> JournalLine:
        account = self._accounts.find_by_code(code)
        name = account.name if account else _DEPR_NAMES.get(code, "")
        return JournalLine(account_code=code, account_name=name, debit=debit, credit=credit)

    @staticmethod
    def _validate(asset: FixedAsset) -> None:
        if not asset.code.strip():
            raise FixedAssetValidationError("Mã tài sản là bắt buộc.")
        if not asset.name.strip():
            raise FixedAssetValidationError("Tên tài sản là bắt buộc.")
        if asset.cost <= 0:
            raise FixedAssetValidationError("Nguyên giá phải lớn hơn 0.")
        if asset.salvage_value < 0:
            raise FixedAssetValidationError("Giá trị thu hồi không được âm.")
        if asset.salvage_value > asset.cost:
            raise FixedAssetValidationError("Giá trị thu hồi không được vượt nguyên giá.")
        if asset.useful_life_months <= 0:
            raise FixedAssetValidationError("Số kỳ khấu hao phải lớn hơn 0.")


def _last_day(year: int, month: int):
    from calendar import monthrange
    from datetime import date

    return date(year, month, monthrange(year, month)[1])
