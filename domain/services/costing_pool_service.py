"""Lấy ba pool chi phí của bảng giá thành thẳng từ sổ cái (TK 1540x).

Trước đây kế toán phải gõ tay tiền nhân công / SX chung / chi phí khác vào bảng
tính giá thành, trong khi các khoản đó vốn đã được hạch toán trong sổ nhật ký
chung (vd bút toán lương ``Nợ 15402 / Có 334``). Hai nơi rời nhau nên số trên
bảng tính không đối chiếu được với số đã ghi sổ.

Service này gom **số phát sinh thuần bên Nợ** của từng tài khoản chi phí sản xuất
trong kỳ để bảng giá thành tự điền:

* ``15402``   → pool nhân công trực tiếp
* ``154032``  → pool chi phí sản xuất chung
* ``154033``  → pool chi phí khác
* ``15403``   → pool sản xuất chung (TK cha; khấu hao máy SX hạch toán thẳng vào
  đây — xem ``PRODUCTION_EXPENSE_ACCOUNTS``)

Ghi Có làm giảm pool, nên bút toán điều chỉnh / hoàn nhập tự trừ ra thay vì phải
sửa tay. Bút toán nháp không được tính.

**Trừ chính bút toán kết chuyển của bảng giá thành** (``GT-155/…`` và
``GT-NVL/…``): chúng do nút Lưu của bảng giá thành sinh ra để tất toán TK 1540x
về 0. Nếu đếm cả chúng thì pool tự trừ đúng bằng số vừa phân bổ — lưu xong mở
lại tab là ô SX chung nhảy sang số âm, lưu tiếp lại về 0, không bao giờ đứng yên.
Chi phí tập hợp là vế Nợ của các bút toán *thực tế* (lương, điện nước, khấu hao),
không phải vế Có của bút toán kết chuyển chính nó.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from data.repositories.journal_repo import JournalRepository
from domain.models.costing import CostPools
from domain.models.journal import EntryStatus
from domain.services.journal_service import JournalService
from domain.services.period_tag import months_in

_ZERO = Decimal("0")

# Khớp mã cụ thể TRƯỚC mã cha: "154032".startswith("15403") cũng đúng, nên nếu
# xét 15403 sớm thì SX chung / chi phí khác bị nuốt hết vào một pool.
_LABOR_ACCOUNT = "15402"
_OVERHEAD_ACCOUNT = "154032"
_OTHER_ACCOUNT = "154033"
_OVERHEAD_PARENT = "15403"

# Bút toán do chính bảng giá thành sinh ra khi lưu (xem
# ``CostingView._post_costing_entries``). Chúng kết chuyển 1540x sang 155 nên có
# vế Có đúng bằng pool; đếm vào thì pool tự triệt tiêu chính nó.
_SELF_GENERATED_REFS = ("GT-155/", "GT-NVL/")

# Bút toán khấu hao TSCĐ hằng tháng: "KH-YYYYMM".
_DEPRECIATION_REF = "KH-"


def pool_of(account_code: str) -> str | None:
    """Tên pool ('labor' / 'overhead' / 'other') của một tài khoản, hoặc ``None``."""
    code = account_code.strip()
    if code.startswith(_OVERHEAD_ACCOUNT):
        return "overhead"
    if code.startswith(_OTHER_ACCOUNT):
        return "other"
    if code.startswith(_OVERHEAD_PARENT):
        return "overhead"
    if code.startswith(_LABOR_ACCOUNT):
        return "labor"
    return None


def _is_self_generated(ref: str) -> bool:
    """Bút toán do nút Lưu của bảng giá thành tạo ra (không phải chi phí tập hợp)."""
    return ref.strip().startswith(_SELF_GENERATED_REFS)


class CostingPoolService:
    def __init__(self, journal: JournalService | None = None) -> None:
        self._journal = journal or JournalService(JournalRepository())

    def pools_for(self, date_from: date, date_to: date) -> CostPools:
        """Số phát sinh thuần bên Nợ của 15402 / 154032 / 154033 trong kỳ.

        Bỏ qua bút toán kết chuyển giá thành do chính bảng này sinh ra
        (``_SELF_GENERATED_REFS``) — nếu tính vào, pool sẽ tự trừ đúng bằng số
        vừa phân bổ và con số trên màn hình đổi sau mỗi lần lưu.
        """
        totals = {"labor": _ZERO, "overhead": _ZERO, "other": _ZERO}
        for entry in self._journal.list_all():
            if entry.status is not EntryStatus.POSTED:
                continue
            if not (date_from <= entry.entry_date <= date_to):
                continue
            if _is_self_generated(entry.ref):
                continue
            for line in entry.lines:
                pool = pool_of(line.account_code)
                if pool is not None:
                    totals[pool] += line.debit - line.credit
        return CostPools(
            labor=totals["labor"],
            overhead=totals["overhead"],
            other=totals["other"],
        )

    def posted_production_depreciation(
        self, year: int, month: int | Iterable[int] | None = None
    ) -> Decimal:
        """Khấu hao máy SX đã NẰM SẴN trong pool SX chung qua bút toán ``KH-…``.

        Nút "Lấy KH máy SX" cộng khấu hao vào ô 154032; nếu bút toán khấu hao
        tháng (``Nợ 15403 / Có 214``) đã được ghi sổ thì số đó vốn đã được
        ``pools_for`` gom vào pool rồi — cộng thêm lần nữa là tính hai lần.
        Trả về phần Nợ của các TK thuộc pool SX chung trong bút toán ``KH-YYYYMM``
        của kỳ (một tháng, dãy tháng của quý, hoặc ``None`` = cả năm).
        """
        refs = {f"{_DEPRECIATION_REF}{year}{m:02d}" for m in months_in(month)}
        total = _ZERO
        for entry in self._journal.list_all():
            if entry.status is not EntryStatus.POSTED or entry.ref not in refs:
                continue
            for line in entry.lines:
                if pool_of(line.account_code) == "overhead":
                    total += line.debit - line.credit
        return total
