"""Kết chuyển giá vốn hàng bán cuối kỳ (kho → TK 632).

Trong kỳ, hóa đơn bán chỉ ghi doanh thu và xuất kho *số lượng*; giá vốn chưa
được ghi. Cuối kỳ — sau khi bảng giá thành đã đủ lương công nhân (15402) — toàn
bộ hàng đã xuất bán được định giá theo **bình quân gia quyền cuối kỳ**:

    ĐG xuất = (TT tồn đầu kỳ + TT nhập trong kỳ) / (SL tồn đầu kỳ + SL nhập)

rồi kết chuyển **một** bút toán ``KC-GV/<kỳ>``: Nợ 632 / Có 155,156 (…).

Nhờ định giá ở bước cuối, lương công nhân về trễ vẫn vào đủ giá thành → giá vốn
khớp giá thành. Bước này còn **định giá lại** chính các bút toán xuất bán trong
sổ kho, để Tồn·TT của báo cáo NXT luôn khớp số dư TK kho trên sổ cái.

Idempotent: :meth:`post` xóa bút toán KC-GV cũ rồi tạo lại; việc định giá lại là
phép gán nên chạy nhiều lần không cộng dồn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from data.repositories.account_repo import AccountRepository
from data.repositories.inventory_repo import InventoryRepository
from data.repositories.invoice_repo import InvoiceRepository
from domain.models.inventory import InventoryMovement
from domain.models.invoice import InvoiceKind, InvoiceStatus
from domain.models.journal import EntryStatus, JournalEntry, JournalLine
from domain.services.closing_service import ClosingService
from domain.services.inventory_service import InventoryService
from domain.services.journal_service import JournalService
from domain.services.period_tag import period_tag

_ZERO = Decimal("0")

COGS_ACCOUNT = "632"        # Giá vốn hàng bán
REF_COGS = "KC-GV"          # tiền tố số chứng từ


@dataclass
class CogsLine:
    """Một tài khoản kho được kết chuyển sang 632."""

    account_code: str
    account_name: str = ""
    quantity: Decimal = _ZERO
    amount: Decimal = _ZERO


@dataclass
class CogsPlan:
    """Bản xem trước của một lượt kết chuyển giá vốn (chưa ghi sổ)."""

    period_tag: str
    date_from: date
    date_to: date
    lines: list[CogsLine] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return sum((ln.amount for ln in self.lines), _ZERO)

    @property
    def is_empty(self) -> bool:
        return self.total <= _ZERO


class CogsService:
    def __init__(
        self,
        journal: JournalService,
        inventory: InventoryService | None = None,
        movements: InventoryRepository | None = None,
        invoices: InvoiceRepository | None = None,
        accounts: AccountRepository | None = None,
        closing: ClosingService | None = None,
    ) -> None:
        self._journal = journal
        self._movements = movements or InventoryRepository()
        self._inventory = inventory or InventoryService(self._movements)
        self._invoices = invoices or InvoiceRepository()
        self._accounts = accounts
        self._closing = closing

    @property
    def _closer(self) -> ClosingService:
        # Lazy so constructing the service never opens a DB connection on import.
        if self._closing is None:
            self._closing = ClosingService()
        return self._closing

    # ----- định giá ------------------------------------------------------

    def _account_names(self) -> dict[str, str]:
        repo = self._accounts or AccountRepository()
        return {a.code: a.name for a in repo.list_all()}

    def _sale_refs(self) -> set[str]:
        """Số chứng từ của các hóa đơn bán đã ghi sổ."""
        return {
            inv.ref for inv in self._invoices.list_all(InvoiceKind.SALE)
            if inv.status is InvoiceStatus.POSTED
        }

    def unit_costs(self, date_from: date, date_to: date) -> dict[str, Decimal]:
        """ĐG bình quân cuối kỳ theo mã hàng: (TT đầu + TT nhập)/(SL đầu + SL nhập).

        Cố ý **không** dùng phần xuất, nên việc định giá lại hàng xuất ở dưới
        không thể hồi tiếp vào chính đơn giá vừa tính.
        """
        prices: dict[str, Decimal] = {}
        for r in self._inventory.compute_nxt(date_from, date_to):
            qty = r.opening_qty + r.in_qty
            value = r.opening_value + r.in_value
            if qty > _ZERO:
                prices[r.item_code] = (value / qty).quantize(Decimal("1"))
        return prices

    def _sale_outs(
        self, date_from: date, date_to: date
    ) -> list[InventoryMovement]:
        """Các bút toán xuất kho của hóa đơn bán trong kỳ."""
        refs = self._sale_refs()
        return [
            m for m in self._movements.list_all()
            if not m.kind.is_inbound
            and date_from <= m.move_date <= date_to
            and m.source_ref in refs
            and m.account_code.strip()
        ]

    # ----- xem trước -----------------------------------------------------

    def plan(self, date_from: date, date_to: date) -> CogsPlan:
        """Gom giá vốn theo từng TK kho, định giá bình quân cuối kỳ.

        Mặt hàng chưa có tồn đầu lẫn nhập trong kỳ (bán âm kho) giữ nguyên đơn
        giá đang ghi trên bút toán, để giá vốn không bị âm thầm về 0.
        """
        prices = self.unit_costs(date_from, date_to)
        names = self._account_names()
        totals: dict[str, tuple[Decimal, Decimal]] = {}
        for m in self._sale_outs(date_from, date_to):
            price = prices.get(m.item_code, m.unit_cost)
            qty, amount = totals.get(m.account_code, (_ZERO, _ZERO))
            totals[m.account_code] = (qty + m.quantity, amount + m.quantity * price)
        return CogsPlan(
            period_tag=period_tag(date_from, date_to),
            date_from=date_from,
            date_to=date_to,
            lines=[
                CogsLine(account_code=code, account_name=names.get(code, ""),
                         quantity=qty, amount=amount)
                for code, (qty, amount) in sorted(totals.items())
                if amount != _ZERO
            ],
        )

    # ----- ghi sổ --------------------------------------------------------

    def is_posted(self, date_from: date, date_to: date) -> bool:
        ref = f"{REF_COGS}/{period_tag(date_from, date_to)}"
        return self._journal.find_by_ref(ref) is not None

    def unpost(self, date_from: date, date_to: date) -> None:
        self._journal.delete_by_ref(f"{REF_COGS}/{period_tag(date_from, date_to)}")

    def reprice(self, date_from: date, date_to: date) -> int:
        """Định giá lại hàng xuất bán trong kỳ theo ĐG bình quân cuối kỳ.

        Trả số bút toán kho đã đổi giá. Giữ sổ kho khớp sổ cái: sau bước này,
        Xuất·TT của NXT bằng đúng số tiền ghi Có TK kho trong bút toán KC-GV.

        Năm đã chốt sổ thì từ chối: đây là ghi đè lịch sử, không phải thêm chứng
        từ mới, nên phải chặn trước khi chạm vào sổ kho.
        """
        self._closer.ensure_open(date_to)
        prices = self.unit_costs(date_from, date_to)
        changed = 0
        for m in self._sale_outs(date_from, date_to):
            price = prices.get(m.item_code)
            if price is None or m.id is None or m.unit_cost == price:
                continue
            self._movements.update_cost(m.id, price)
            changed += 1
        return changed

    def post(self, date_from: date, date_to: date) -> JournalEntry | None:
        """Định giá lại + kết chuyển giá vốn sang 632. ``None`` nếu kỳ không có bán.

        Kiểm tra chốt sổ NGAY ĐẦU: ``reprice`` ghi đè đơn giá trên sổ kho trước
        khi bút toán được tạo, nên nếu để :meth:`JournalService.create` báo lỗi
        thì sổ kho đã bị sửa mất rồi.
        """
        self._closer.ensure_open(date_to)
        self.unpost(date_from, date_to)
        self.reprice(date_from, date_to)
        plan = self.plan(date_from, date_to)
        if plan.is_empty:
            return None
        names = self._account_names()
        return self._journal.create(JournalEntry(
            ref=f"{REF_COGS}/{plan.period_tag}",
            entry_date=date_to,
            description=f"Kết chuyển giá vốn hàng bán {plan.period_tag}",
            status=EntryStatus.POSTED,
            lines=[
                JournalLine(account_code=COGS_ACCOUNT,
                            account_name=names.get(COGS_ACCOUNT, "Giá vốn hàng bán"),
                            description="Giá vốn hàng xuất bán",
                            debit=plan.total)
            ] + [
                JournalLine(account_code=ln.account_code,
                            account_name=ln.account_name,
                            description="Kết chuyển giá vốn",
                            credit=ln.amount)
                for ln in plan.lines
            ],
        ))
