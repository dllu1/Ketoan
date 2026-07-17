"""DashboardService: live KPIs, trend, expense mix & aging from the ledger.

Every figure is aggregated from POSTED journal entries (plus invoices for
receivables aging), so the dashboard always matches the reports and the books.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from data.repositories.account_repo import AccountRepository
from data.repositories.invoice_repo import InvoiceRepository
from data.repositories.journal_repo import JournalRepository
from data.repositories.partner_repo import PartnerRepository
from domain.models.account import AccountKind
from domain.models.invoice import InvoiceKind, InvoiceStatus, PaymentMethod
from domain.models.journal import EntryStatus
from domain.models.partner import PartnerType

_Z = Decimal("0")

_KIND_BY_DIGIT = {
    "1": AccountKind.ASSET, "2": AccountKind.ASSET,
    "3": AccountKind.LIABILITY, "4": AccountKind.EQUITY,
    "5": AccountKind.REVENUE, "6": AccountKind.EXPENSE,
    "7": AccountKind.REVENUE, "8": AccountKind.EXPENSE,
    "9": AccountKind.OTHER,
}
_INVENTORY_PREFIXES = ("151", "152", "153", "154", "155", "156", "157")


@dataclass
class Kpi:
    label_vi: str
    label_en: str
    value: Decimal
    delta_pct: Decimal
    trend: str            # "up" | "down" | "flat"
    hint: str
    spark: list[float] = field(default_factory=list)


@dataclass
class TrendMonth:
    label: str
    revenue: Decimal
    cost: Decimal
    opex: Decimal


@dataclass
class ExpenseSlice:
    label_vi: str
    label_en: str
    amount: Decimal
    pct: float


@dataclass
class AgedSlice:
    bucket_vi: str
    bucket_en: str
    amount: Decimal


@dataclass
class CashPosition:
    code: str
    name: str
    amount: Decimal


@dataclass
class OverdueInvoice:
    ref: str
    invoice_no: str
    partner_name: str
    amount: Decimal
    days_overdue: int


@dataclass
class DashboardData:
    period_label: str
    kpis: list[Kpi]
    trend: list[TrendMonth]
    expense_mix: list[ExpenseSlice]
    expense_total: Decimal
    aged: list[AgedSlice]
    cash_positions: list[CashPosition]
    overdue_count: int
    overdue_details: list[OverdueInvoice]
    has_data: bool


class DashboardService:
    def __init__(
        self,
        journal_repo: JournalRepository | None = None,
        account_repo: AccountRepository | None = None,
        invoice_repo: InvoiceRepository | None = None,
        partner_repo: PartnerRepository | None = None,
        today: date | None = None,
    ) -> None:
        self._journal = journal_repo or JournalRepository()
        self._accounts = account_repo or AccountRepository()
        self._invoices = invoice_repo or InvoiceRepository()
        self._partners = partner_repo or PartnerRepository()
        self._today = today or date.today()

    def build(self) -> DashboardData:
        entries = [e for e in self._journal.list_all()
                   if e.status is EntryStatus.POSTED]
        if not entries:
            return DashboardData(
                period_label="—", kpis=[], trend=[], expense_mix=[],
                expense_total=_Z, aged=[], cash_positions=[],
                overdue_count=0, overdue_details=[], has_data=False,
            )

        ref = max(e.entry_date for e in entries)
        months = _trailing_months(ref.year, ref.month, 12)
        ref_ym = (ref.year, ref.month)

        # Một lượt quét sổ dựng mọi tổng hợp (doanh thu / giá vốn / chi phí + số
        # dư các nhóm + cơ cấu chi phí + vị thế tiền) thay cho 9 lần quét riêng.
        agg = self._scan(entries, set(months))
        rev, cogs, opex = agg["rev"], agg["cogs"], agg["opex"]
        bal_ar, bal_ap = agg["ar"], agg["ap"]
        bal_cash, bal_inv = agg["cash"], agg["inv"]

        gross = {ym: rev.get(ym, _Z) - cogs.get(ym, _Z) for ym in months}

        kpis = [
            self._flow_kpi("Doanh thu tháng", "Revenue MTD", rev, months, ref_ym,
                           hint=f"tháng {ref_ym[1]:02d}/{ref_ym[0]}"),
            self._flow_kpi("Lợi nhuận gộp", "Gross profit", gross, months, ref_ym,
                           hint=self._margin_hint(gross.get(ref_ym, _Z), rev.get(ref_ym, _Z))),
            self._balance_kpi("Phải thu KH", "Receivables", bal_ar, months, ref_ym,
                              sign=1, hint=self._receivable_hint()),
            self._balance_kpi("Phải trả NCC", "Payables", bal_ap, months, ref_ym,
                              sign=-1, hint=self._partner_hint(PartnerType.SUPPLIER, "NCC")),
            self._balance_kpi("Tiền & tương đương", "Cash & equiv.", bal_cash, months,
                              ref_ym, sign=1, hint="Quỹ + ngân hàng"),
            self._balance_kpi("Tồn kho", "Inventory", bal_inv, months, ref_ym,
                              sign=1, hint=f"{self._sku_count()} mặt hàng"),
        ]

        trend = [
            TrendMonth(_short_label(y, m), rev.get((y, m), _Z),
                       cogs.get((y, m), _Z), opex.get((y, m), _Z))
            for (y, m) in months
        ]

        expense_mix, expense_total = self._expense_slices(agg["exp"])
        aged = self._aged_receivables()
        cash_positions = self._cash_positions_from(agg["cash_pos"])
        overdue_details = self._overdue_invoices()

        return DashboardData(
            period_label=f"{ref_ym[1]:02d}/{ref_ym[0]}",
            kpis=kpis, trend=trend, expense_mix=expense_mix,
            expense_total=expense_total, aged=aged,
            cash_positions=cash_positions, overdue_count=len(overdue_details),
            overdue_details=overdue_details, has_data=True,
        )

    # ----- KPI builders -----------------------------------------------------

    def _flow_kpi(self, vi, en, series, months, ref_ym, *, hint) -> Kpi:
        spark = [float(series.get(ym, _Z)) for ym in months]
        cur = series.get(ref_ym, _Z)
        prev = series.get(_prev_ym(ref_ym), _Z)
        return Kpi(vi, en, cur, *_delta(cur, prev), hint=hint, spark=spark)

    def _balance_kpi(self, vi, en, monthly_net, months, ref_ym, *, sign, hint) -> Kpi:
        # Running month-end balance from cumulative monthly nets.
        ordered = sorted(set(list(monthly_net) + months))
        run = _Z
        full: dict[tuple[int, int], Decimal] = {}
        for ym in ordered:
            run += monthly_net.get(ym, _Z)
            full[ym] = run
        spark = [float(_at_or_before(full, ym) * sign) for ym in months]
        cur = _at_or_before(full, ref_ym) * sign
        prev = _at_or_before(full, _prev_ym(ref_ym)) * sign
        return Kpi(vi, en, cur, *_delta(cur, prev), hint=hint, spark=spark)

    # ----- aggregation helpers ---------------------------------------------

    def _scan(self, entries, window: set) -> dict[str, dict]:
        """Một lượt quét sổ dựng mọi tổng hợp cho dashboard.

        Trước đây build() gọi 9 hàm quét sổ riêng (_flow×3, _cumulative×4,
        _expense_mix, _cash_positions) — mỗi hàm duyệt lại toàn bộ bút toán×dòng,
        tức O(9·số dòng). Gộp về một vòng lặp: O(số dòng). Kết quả từng nhóm giữ
        nguyên (đã khóa bằng test_dashboard_service).
        """
        rev: dict = {}; cogs: dict = {}; opex: dict = {}
        ar: dict = {}; ap: dict = {}; cash: dict = {}; inv: dict = {}
        exp: dict = {}; cash_pos: dict = {}
        for entry in entries:
            ym = (entry.entry_date.year, entry.entry_date.month)
            in_window = ym in window
            for line in entry.lines:
                code = line.account_code
                net = line.debit - line.credit          # Nợ − Có
                kind = self._kind(code)
                if kind is AccountKind.REVENUE:
                    rev[ym] = rev.get(ym, _Z) - net     # doanh thu = Có − Nợ
                if code.startswith("632"):
                    cogs[ym] = cogs.get(ym, _Z) + net
                elif kind is AccountKind.EXPENSE:
                    opex[ym] = opex.get(ym, _Z) + net
                if code.startswith("131"):
                    ar[ym] = ar.get(ym, _Z) + net
                elif code.startswith("331"):
                    ap[ym] = ap.get(ym, _Z) + net
                if code.startswith(("111", "112")):
                    cash[ym] = cash.get(ym, _Z) + net
                    cash_pos[code[:3]] = cash_pos.get(code[:3], _Z) + net
                elif code.startswith(_INVENTORY_PREFIXES):
                    inv[ym] = inv.get(ym, _Z) + net
                if in_window and self._kind(code[:3]) is AccountKind.EXPENSE:
                    exp[code[:3]] = exp.get(code[:3], _Z) + net
        return {
            "rev": rev, "cogs": cogs, "opex": opex, "ar": ar, "ap": ap,
            "cash": cash, "inv": inv, "exp": exp, "cash_pos": cash_pos,
        }

    def _expense_slices(self, totals: dict[str, Decimal]) -> tuple[list[ExpenseSlice], Decimal]:
        totals = {c: v for c, v in totals.items() if v > 0}
        grand = sum(totals.values(), _Z)
        if grand <= 0:
            return [], _Z
        ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        slices: list[ExpenseSlice] = []
        head, tail = ranked[:5], ranked[5:]
        for code, amount in head:
            slices.append(ExpenseSlice(
                self._name(code), code, amount,
                float((amount / grand * 100).quantize(Decimal("0.1"))),
            ))
        if tail:
            other = sum((v for _, v in tail), _Z)
            slices.append(ExpenseSlice(
                "Chi phí khác", "Other", other,
                float((other / grand * 100).quantize(Decimal("0.1"))),
            ))
        return slices, grand

    def _cash_positions_from(self, totals: dict[str, Decimal]) -> list[CashPosition]:
        return [
            CashPosition(code, self._name(code), amount)
            for code, amount in sorted(totals.items())
            if amount != _Z
        ]

    def _aged_receivables(self) -> list[AgedSlice]:
        buckets = [
            ("Trong hạn", "0-30", 0, 30),
            ("31–60 ngày", "31-60", 31, 60),
            ("61–90 ngày", "61-90", 61, 90),
            ("> 90 ngày", "90+", 91, 10**6),
        ]
        sums = {b[1]: _Z for b in buckets}
        for inv in self._invoices.list_all(InvoiceKind.SALE):
            if inv.status is not InvoiceStatus.POSTED:
                continue
            if inv.payment_method is not PaymentMethod.CREDIT:
                continue
            age = (self._today - inv.invoice_date).days
            for vi, key, lo, hi in buckets:
                if lo <= age <= hi:
                    sums[key] += inv.grand_total
                    break
        return [AgedSlice(vi, key, sums[key]) for vi, key, *_ in buckets]

    def _overdue_invoices(self) -> list[OverdueInvoice]:
        # Cache theo instance: build() và _receivable_hint() cùng cần danh sách
        # này, tránh quét lại toàn bộ hóa đơn lần thứ hai.
        cached = getattr(self, "_overdue_cache", None)
        if cached is not None:
            return cached
        out: list[OverdueInvoice] = []
        for inv in self._invoices.list_all(InvoiceKind.SALE):
            days = (self._today - inv.invoice_date).days
            if (inv.status is InvoiceStatus.POSTED
                    and inv.payment_method is PaymentMethod.CREDIT
                    and days > 30):
                out.append(OverdueInvoice(
                    ref=inv.ref,
                    invoice_no=inv.invoice_no or inv.ref,
                    partner_name=inv.partner_name or "Khách lẻ",
                    amount=inv.grand_total,
                    days_overdue=days,
                ))
        out.sort(key=lambda o: o.days_overdue, reverse=True)
        self._overdue_cache = out
        return out

    def _overdue_count(self) -> int:
        return len(self._overdue_invoices())

    # ----- lookups & hints --------------------------------------------------

    def _account_map(self):
        cached = getattr(self, "_acc_cache", None)
        if cached is None:
            cached = {a.code: a for a in self._accounts.list_all()}
            self._acc_cache = cached
        return cached

    def _name(self, code: str) -> str:
        account = self._account_map().get(code) or self._account_map().get(code[:3])
        return account.name if account else code

    def _kind(self, code: str) -> AccountKind:
        account = self._account_map().get(code) or self._account_map().get(code[:3])
        if account and account.kind:
            try:
                return AccountKind(account.kind)
            except ValueError:
                pass
        return _KIND_BY_DIGIT.get(code[:1], AccountKind.OTHER)

    def _sku_count(self) -> int:
        from data.repositories.item_repo import ItemRepository
        return len(ItemRepository().list_all())

    def _receivable_hint(self) -> str:
        customers = len(self._partners.list_all(PartnerType.CUSTOMER))
        overdue = self._overdue_count()
        return f"{customers} KH · {overdue} quá hạn"

    def _partner_hint(self, ptype, noun) -> str:
        return f"{len(self._partners.list_all(ptype))} {noun}"

    @staticmethod
    def _margin_hint(gross: Decimal, revenue: Decimal) -> str:
        if revenue <= 0:
            return "biên —"
        return f"biên {gross / revenue * 100:.1f}%"


# ----- module helpers -------------------------------------------------------


def _trailing_months(year: int, month: int, count: int) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    y, m = year, month
    for _ in range(count):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(months))


def _prev_ym(ym: tuple[int, int]) -> tuple[int, int]:
    y, m = ym
    return (y - 1, 12) if m == 1 else (y, m - 1)


def _at_or_before(full: dict[tuple[int, int], Decimal], ym: tuple[int, int]) -> Decimal:
    best = _Z
    for key in sorted(full):
        if key <= ym:
            best = full[key]
        else:
            break
    return best


def _short_label(year: int, month: int) -> str:
    return f"{month:02d}/{year % 100:02d}"


def _delta(cur: Decimal, prev: Decimal) -> tuple[Decimal, str]:
    if prev == 0:
        return (Decimal("0"), "flat")
    pct = (cur - prev) / abs(prev) * 100
    trend = "up" if pct > 0 else "down" if pct < 0 else "flat"
    return (abs(pct).quantize(Decimal("0.1")), trend)
