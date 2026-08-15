"""Fixed asset rules: straight-line depreciation + monthly posting to 214."""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from data.repositories.account_repo import AccountRepository
from data.repositories.fixed_asset_repo import FixedAssetRepository
from domain.models.fixed_asset import FixedAsset
from domain.models.journal import EntryStatus, JournalEntry, JournalLine
from domain.services.closing_service import ClosingService
from domain.services.journal_service import JournalService
from domain.services.period_tag import months_in

_ACCUMULATED_DEPR_ACCOUNT = "214"
# Số chứng từ khấu hao tháng: KH-YYYYMM
_DEPR_REF = re.compile(r"KH-(\d{4})(\d{2})")
_DEPR_NAMES = {
    "214": "Hao mòn tài sản cố định",
    "15403": "Chi phí sản xuất chung (giá thành)",
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
        closing: ClosingService | None = None,
    ) -> None:
        self._repo = repo
        self._journal = journal
        self._accounts = account_repo or AccountRepository()
        self._closing = closing

    @property
    def _closer(self) -> ClosingService:
        # Lazy so constructing the service never opens a DB connection on import.
        if self._closing is None:
            self._closing = ClosingService()
        return self._closing

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
        saved = self._repo.update(asset)
        # Đổi TK chi phí (hay nguyên giá, số kỳ…) phải kéo theo bút toán khấu hao
        # ĐÃ ghi: nếu không, tiền vẫn nằm ở tài khoản cũ và người dùng phải nhớ
        # bấm "Ghi khấu hao kỳ" lại cho từng tháng.
        self.resync_posted_depreciation()
        return saved

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

    def production_depreciation(
        self, year: int, month: int | Iterable[int] | None = None
    ) -> Decimal:
        """Khấu hao máy móc dùng cho sản xuất (TK 15403/627) của kỳ.

        ``month`` nhận một tháng, một dãy tháng (kỳ theo quý) hoặc ``None`` =
        cả năm, khớp với bộ chọn kỳ của bảng tính giá thành.
        Đây là phần khấu hao phải nằm trong pool chi phí sản xuất chung."""
        months = months_in(month)
        total = Decimal("0")
        for asset in self._repo.list_all():
            if not asset.feeds_production_cost:
                continue
            for m in months:
                total += asset.depreciation_for(year, m)
        return total

    def post_monthly_depreciation(self, year: int, month: int) -> JournalEntry | None:
        """Ghi bút toán khấu hao tháng: Nợ chi phí / Có 214 cho mọi TSCĐ đang KH.

        Idempotent theo số chứng từ ``KH-YYYYMM``; trả về None nếu không có
        khấu hao trong kỳ."""
        if self._journal is None:
            raise FixedAssetValidationError("Chưa cấu hình sổ nhật ký để ghi khấu hao.")
        # Chặn TRƯỚC khi xóa bút toán cũ: delete_by_ref không kiểm tra chốt sổ,
        # nên nếu để bước create báo lỗi thì bút toán của năm đã chốt đã mất rồi.
        entry_date = _last_day(year, month)
        self._closer.ensure_open(entry_date)
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
                entry_date=entry_date,
                description=f"Khấu hao TSCĐ tháng {month:02d}/{year}",
                status=EntryStatus.POSTED,
                lines=lines,
            )
        )

    def posted_depreciation_periods(self) -> list[tuple[int, int]]:
        """(năm, tháng) của mọi bút toán khấu hao ``KH-YYYYMM`` đang có trong sổ."""
        if self._journal is None:
            return []
        periods: set[tuple[int, int]] = set()
        for entry in self._journal.list_all():
            match = _DEPR_REF.fullmatch(entry.ref.strip())
            if match:
                periods.add((int(match.group(1)), int(match.group(2))))
        return sorted(periods)

    def resync_posted_depreciation(self) -> list[str]:
        """Ghi lại các bút toán khấu hao đã có theo cấu hình TSCĐ hiện tại.

        Gọi sau khi sửa tài sản: số khấu hao chuyển sang đúng TK chi phí vừa
        chọn thay vì nằm lại ở tài khoản cũ. Chỉ đụng vào những tháng người dùng
        đã chủ động ghi khấu hao — không tự ghi thêm tháng mới. Tháng thuộc năm
        đã chốt sổ được bỏ qua chứ không làm hỏng cả thao tác lưu.
        """
        if self._journal is None:
            return []
        reposted: list[str] = []
        for year, month in self.posted_depreciation_periods():
            try:
                entry = self.post_monthly_depreciation(year, month)
            except Exception:  # noqa: BLE001 — năm đã chốt sổ / bút toán bị khóa
                continue
            if entry is not None:
                reposted.append(entry.ref)
        return reposted

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
        if not asset.expense_account.strip():
            raise FixedAssetValidationError("Phải chọn tài khoản chi phí khấu hao.")
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
