"""Demo data seeding — populate every module with a realistic 12-month dataset.

Run once to explore the app with live numbers::

    python seed_demo.py            # seed if empty
    python seed_demo.py --reset    # wipe transactional data and reseed

Everything is generated through the real services, so the journal, inventory
NXT, VAT/CIT reports and dashboard all stay internally consistent.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from data.database import get_connection, init_database
from data.repositories.account_repo import AccountRepository
from data.repositories.costing_repo import CostingRepository
from data.repositories.fixed_asset_repo import FixedAssetRepository
from data.repositories.inventory_repo import InventoryRepository
from data.repositories.invoice_repo import InvoiceRepository
from data.repositories.item_repo import ItemRepository
from data.repositories.journal_repo import JournalRepository
from data.repositories.material_sheet_repo import MaterialSheetRepository
from data.repositories.partner_repo import PartnerRepository
from data.repositories.settings_repo import SettingsRepository
from domain.models.costing import CostingInput, CostPools
from domain.models.fixed_asset import FixedAsset
from domain.models.material_sheet import MaterialLine, MaterialSheet
from domain.models.invoice import (
    Invoice,
    InvoiceKind,
    InvoiceLine,
    InvoiceStatus,
    PaymentMethod,
)
from domain.models.item import Item, ItemCategory
from domain.models.journal import EntryStatus, JournalEntry, JournalLine
from domain.models.partner import Partner, PartnerType
from domain.services.account_service import AccountService
from domain.services.costing_service import CostingService
from domain.services.fixed_asset_service import FixedAssetService
from domain.services.inventory_service import InventoryService
from domain.services.journal_service import JournalService
from domain.services.material_sheet_service import MaterialSheetService
from domain.services.purchase_service import PurchaseService
from domain.services.sales_service import SalesService

_SEED_FLAG = "demo_seeded"
_Z = Decimal("0")
_PAYMENTS = [PaymentMethod.BANK, PaymentMethod.CREDIT, PaymentMethod.CASH]

_CUSTOMERS = [
    ("KH001", "Công ty TNHH Cơ khí Đại Phát", "0312345678", "Q.Bình Tân, TP.HCM"),
    ("KH002", "Công ty CP Xây dựng Hòa Bình", "0301122334", "Q.3, TP.HCM"),
    ("KH003", "Nhà máy Nhiệt điện Vĩnh Tân", "0408899776", "Bình Thuận"),
    ("KH004", "Công ty TNHH Sản xuất Tân Tiến", "0315566778", "Bình Dương"),
    ("KH005", "Công ty CP Thép Nam Kim", "0322233445", "Đồng Nai"),
    ("KH006", "Công ty TNHH M&E Toàn Cầu", "0317788990", "Q.7, TP.HCM"),
]

_SUPPLIERS = [
    ("NCC001", "Công ty TNHH Thép Hòa Phát", "0101234567", "Hưng Yên"),
    ("NCC002", "Công ty CP Que hàn Kim Tín", "0309988776", "Bình Dương"),
    ("NCC003", "Công ty TNHH Thiết bị Jasic VN", "0312121212", "Q.Tân Phú, TP.HCM"),
    ("NCC004", "Công ty CP Van & Phụ kiện Sài Gòn", "0304545454", "Q.12, TP.HCM"),
]

# code, name, category, unit, cost, sale_price, vat
_ITEMS = [
    ("VT001", "Thép tấm SS400 10ly", ItemCategory.MATERIAL, "Kg", 18_000, 29_000, 10),
    ("VT002", "Que hàn Kim Tín 3.2mm", ItemCategory.MATERIAL, "Kg", 35_000, 56_000, 10),
    ("CC001", "Máy hàn Jasic 250A", ItemCategory.TOOL, "Cái", 4_200_000, 6_800_000, 10),
    ("HH001", "Ống thép mạ kẽm D60", ItemCategory.GOOD, "Cây", 145_000, 235_000, 10),
    ("HH002", "Van bi inox 304 DN50", ItemCategory.GOOD, "Cái", 320_000, 520_000, 8),
    ("TP001", "Tủ điện công nghiệp 3 pha", ItemCategory.PRODUCT, "Bộ", 8_500_000, 14_500_000, 10),
]

# Hệ số nhân khối lượng giao dịch để demo có quy mô doanh thu hợp lý.
_QTY = 3

# ----- production-costing worksheets (Phase 5) ----------------------------
# Two worksheets the accountant edits by hand; seeded so the Kho hàng tabs
# open with live numbers. Seeded for the whole-year period "2026" (the default
# view) and the current month "2026-06" so the period selector can be tried.
#
# Worksheet demo periods: whole-year (default view) + current month.
_WORKSHEET_PERIODS = ("2026", "2026-06")

# Bảng kê N–X–T NVL chính: (code, name, unit, đơn giá, đầu kỳ SL, nhập SL,
# xuất SL). Giá trị (TT) = SL × đơn giá; tồn cuối kỳ = đầu kỳ + nhập − xuất and
# is kept non-negative on every row (the service refuses a negative closing).
#
# Only *off-ledger* raw materials live here (NVL003–006). Catalog materials like
# VT001/VT002 already have real mua/bán movements, so they flow into the sheet
# read-only from the inventory ledger automatically — seeding them here would be
# ignored. Manual rows are seeded for ONE period only: the sheet pushes them into
# the ledger, and pushing the same material from both a year and a month sheet
# would double-count in Nhập–Xuất–Tồn.
_MATERIAL_SHEET = {
    "2026": [
        ("NVL003", "Tôn mạ kẽm 1.5ly", "Kg", 22_000, 5_000, 8_000, 9_500),
        ("NVL004", "Sơn tĩnh điện RAL 7035", "Kg", 65_000, 800, 1_500, 1_900),
        ("NVL005", "Thanh đồng cái 50x5", "Kg", 280_000, 300, 600, 700),
        ("NVL006", "Dây điện Cadivi CV 2.5", "m", 12_000, 4_000, 10_000, 11_500),
    ],
}

# Bảng tính giá thành sản phẩm: pools (nhân công 15402 / SX chung 154032 /
# khác 154033) are allocated across products by NVL ratio at compute time, so
# only (pools, products) are stored. products: (code, name, SL, NVL 15401).
_COSTING_SHEET = {
    "2026": (
        (280_000_000, 168_000_000, 84_000_000),
        [
            ("TP001", "Tủ điện công nghiệp 3 pha", 90, 540_000_000),
            ("TP002", "Tủ điện điều khiển bơm PCCC", 60, 300_000_000),
            ("TP003", "Khung kèo thép mạ kẽm", 120, 360_000_000),
            ("TP004", "Máng cáp sơn tĩnh điện", 200, 200_000_000),
        ],
    ),
    "2026-06": (
        (24_200_000, 14_520_000, 7_260_000),
        [
            ("TP001", "Tủ điện công nghiệp 3 pha", 8, 48_000_000),
            ("TP002", "Tủ điện điều khiển bơm PCCC", 5, 25_000_000),
            ("TP003", "Khung kèo thép mạ kẽm", 10, 30_000_000),
            ("TP004", "Máng cáp sơn tĩnh điện", 18, 18_000_000),
        ],
    ),
}


def seed_demo(*, reset: bool = False) -> bool:
    """Seed demo data. Returns True if data was written, False if skipped."""
    init_database()
    settings = SettingsRepository()
    if settings.get(_SEED_FLAG) == "1" and not reset:
        return False
    if reset:
        _wipe()

    AccountService(AccountRepository()).ensure_seeded()

    partners = PartnerRepository()
    for code, name, tax, addr in _CUSTOMERS:
        partners.insert(Partner(code=code, name=name, type=PartnerType.CUSTOMER,
                                tax_code=tax, address=addr))
    for code, name, tax, addr in _SUPPLIERS:
        partners.insert(Partner(code=code, name=name, type=PartnerType.SUPPLIER,
                                tax_code=tax, address=addr))

    items = ItemRepository()
    item_by_code: dict[str, Item] = {}
    cost_by_code: dict[str, Decimal] = {}
    for code, name, cat, unit, cost, sale, vat in _ITEMS:
        item = items.insert(Item(code=code, name=name, category=cat, unit=unit,
                                 unit_price=Decimal(sale), vat_rate=Decimal(vat)))
        item_by_code[code] = item
        cost_by_code[code] = Decimal(cost)

    _Seeder(item_by_code, cost_by_code, partners).run()
    seed_worksheets()

    settings.set(_SEED_FLAG, "1")
    return True


def seed_worksheets() -> None:
    """Seed the two production-costing worksheets (NXT NVL chính + giá thành).

    Idempotent: each period is rewritten wholesale (the worksheets are edited
    as one document per period), so calling this repeatedly just refreshes the
    seeded numbers. Safe to run on a database that already has demo data — it
    only touches the worksheet tables. Goes through the real services so the
    same validation the UI uses (no negative closing balance) is exercised.
    """
    init_database()

    material_service = MaterialSheetService(MaterialSheetRepository())
    for period_key in _WORKSHEET_PERIODS:
        rows = _MATERIAL_SHEET.get(period_key, [])   # () clears stale manual rows
        lines = [
            MaterialLine(
                code=code, name=name, unit=unit,
                opening_price=Decimal(price), opening_qty=Decimal(open_qty),
                opening_value=Decimal(price) * Decimal(open_qty),
                in_price=Decimal(price), in_qty=Decimal(in_qty),
                in_value=Decimal(price) * Decimal(in_qty),
                out_price=Decimal(price), out_qty=Decimal(out_qty),
                out_value=Decimal(price) * Decimal(out_qty),
            )
            for code, name, unit, price, open_qty, in_qty, out_qty in rows
        ]
        material_service.save(MaterialSheet(period_key=period_key, lines=lines))

    costing_service = CostingService(CostingRepository())
    for period_key, (pool_amounts, products) in _COSTING_SHEET.items():
        labor, overhead, other = pool_amounts
        pools = CostPools(
            labor=Decimal(labor), overhead=Decimal(overhead), other=Decimal(other)
        )
        inputs = [
            CostingInput(
                code=code, name=name,
                quantity=Decimal(qty), material_cost=Decimal(nvl),
            )
            for code, name, qty, nvl in products
        ]
        costing_service.save(period_key, inputs, pools)


class _Seeder:
    def __init__(self, items, costs, partners) -> None:
        self._items = items
        self._costs = costs
        self._partners = partners
        self._accounts = AccountRepository()
        self._journal = JournalService(JournalRepository())
        inventory = InventoryService(InventoryRepository(), ItemRepository())
        self._sales = SalesService(
            InvoiceRepository(), inventory, self._journal,
            PartnerRepository(), self._accounts,
        )
        self._purchases = PurchaseService(
            InvoiceRepository(), inventory, self._journal,
            PartnerRepository(), self._accounts,
        )
        self._assets = FixedAssetService(
            FixedAssetRepository(), self._journal, self._accounts
        )
        self._n = 0

    def run(self) -> None:
        months = [(2025, m) for m in range(7, 13)] + [(2026, m) for m in range(1, 7)]

        # Góp vốn điều lệ + mở quỹ tiền (Nợ 111/112 / Có 411).
        self._je("GV-OPEN", date(2025, 7, 1), "Góp vốn điều lệ ban đầu", [
            ("111", Decimal("1500000000"), _Z),
            ("112", Decimal("7000000000"), _Z),
            ("411", _Z, Decimal("8500000000")),
        ])

        self._seed_fixed_assets()
        # Nhập kho ban đầu (đủ tồn cho giá vốn các tháng sau).
        self._purchase(date(2025, 7, 2), 0, [
            ("VT001", 24000), ("VT002", 3600), ("CC001", 60),
            ("HH001", 4500), ("HH002", 1200), ("TP001", 90),
        ])

        for i, (y, m) in enumerate(months):
            growth = Decimal("1") + Decimal("0.05") * i
            self._monthly_purchase(y, m, i)
            self._monthly_sales(y, m, i, growth)
            self._monthly_expenses(y, m, growth)
            self._assets.post_monthly_depreciation(y, m)

        self._draft_sales()

    def _draft_sales(self) -> None:
        """A few unposted (nháp) sales orders — drive the Sales tab badge."""
        drafts = [
            (date(2026, 6, 12), 0, [("HH001", 90), ("VT001", 600)]),
            (date(2026, 6, 18), 2, [("TP001", 4)]),
            (date(2026, 6, 24), 4, [("HH002", 50), ("VT002", 80)]),
        ]
        for day, ci, basket in drafts:
            customer = _CUSTOMERS[ci % len(_CUSTOMERS)]
            lines = [self._line(code, qty, self._items[code].unit_price)
                     for code, qty in basket]
            self._n += 1
            self._sales.create(Invoice(
                ref=f"BH{self._n:04d}",
                invoice_no="",
                serial="1C26TAA",
                invoice_date=day,
                kind=InvoiceKind.SALE,
                status=InvoiceStatus.DRAFT,
                payment_method=PaymentMethod.CREDIT,
                partner_code=customer[0], partner_name=customer[1],
                partner_tax_code=customer[2],
                description="Đơn hàng chờ ghi sổ",
                lines=lines,
            ))

    # ----- transaction builders --------------------------------------------

    def _seed_fixed_assets(self) -> None:
        specs = [
            ("TS001", "Xe nâng Toyota 2.5 tấn", "642", 480_000_000, 72),
            ("TS002", "Máy cắt CNC Plasma", "627", 1_200_000_000, 96),
        ]
        for code, name, expense, cost, life in specs:
            self._assets.create(FixedAsset(
                code=code, name=name, asset_account="211", expense_account=expense,
                cost=Decimal(cost), useful_life_months=life,
                start_date=date(2025, 7, 1),
            ))
            # Ghi tăng nguyên giá: Nợ 211 / Có 112.
            self._je(f"MS-{code}", date(2025, 7, 1), f"Mua sắm {name}", [
                ("211", Decimal(cost), _Z),
                ("112", _Z, Decimal(cost)),
            ])

    def _monthly_purchase(self, y: int, m: int, i: int) -> None:
        plan = [
            [("VT001", 3600), ("HH001", 750)],
            [("VT002", 600), ("HH002", 240)],
            [("CC001", 12), ("TP001", 18)],
        ][i % 3]
        self._purchase(date(y, m, 4), i, plan)

    def _purchase(self, day: date, i: int, plan: list[tuple[str, int]]) -> None:
        supplier = _SUPPLIERS[i % len(_SUPPLIERS)]
        lines = [self._line(code, qty, self._costs[code]) for code, qty in plan]
        self._n += 1
        inv = Invoice(
            ref=f"PN{self._n:04d}",
            invoice_no=f"{2000 + self._n}",
            serial="1C25TNC",
            invoice_date=day,
            kind=InvoiceKind.PURCHASE,
            status=InvoiceStatus.POSTED,
            payment_method=_PAYMENTS[i % 3],
            partner_code=supplier[0], partner_name=supplier[1],
            partner_tax_code=supplier[2],
            description="Nhập mua vật tư, hàng hóa",
            lines=lines,
        )
        self._purchases.create(inv)

    def _monthly_sales(self, y: int, m: int, i: int, growth: Decimal) -> None:
        baskets = [
            [("HH001", 180), ("VT001", 1200)],
            [("TP001", 6), ("HH002", 75)],
            [("VT002", 120), ("CC001", 3), ("HH001", 90)],
        ]
        for s, basket in enumerate(baskets):
            day = date(y, m, 10 + s * 8)
            customer = _CUSTOMERS[(i + s) % len(_CUSTOMERS)]
            lines = [
                self._line(code, int(Decimal(qty) * growth), self._items[code].unit_price)
                for code, qty in basket
            ]
            self._n += 1
            inv = Invoice(
                ref=f"BH{self._n:04d}",
                invoice_no=f"{2000 + self._n}",
                serial="1C26TAA",
                invoice_date=day,
                kind=InvoiceKind.SALE,
                status=InvoiceStatus.POSTED,
                payment_method=_PAYMENTS[(i + s) % 3],
                partner_code=customer[0], partner_name=customer[1],
                partner_tax_code=customer[2],
                description="Bán hàng hóa, thành phẩm",
                lines=lines,
            )
            self._sales.create(inv)

    def _monthly_expenses(self, y: int, m: int, growth: Decimal) -> None:
        last = _last_day(y, m)
        salary = (Decimal("120000000") * growth).quantize(Decimal("1"))
        utilities = (Decimal("28000000") * growth).quantize(Decimal("1"))
        selling = (Decimal("45000000") * growth).quantize(Decimal("1"))
        self._je(f"PC-L{y}{m:02d}", last, "Chi lương nhân viên", [
            ("642", salary, _Z), ("112", _Z, salary),
        ])
        self._je(f"PC-U{y}{m:02d}", last, "Chi điện nước, vận hành xưởng", [
            ("627", utilities, _Z), ("111", _Z, utilities),
        ])
        self._je(f"PC-S{y}{m:02d}", last, "Chi phí bán hàng, vận chuyển", [
            ("641", selling, _Z), ("112", _Z, selling),
        ])

    # ----- helpers ----------------------------------------------------------

    def _line(self, code: str, qty: int, price: Decimal) -> InvoiceLine:
        item = self._items[code]
        return InvoiceLine(
            item_code=code, item_name=item.name, unit=item.unit,
            quantity=Decimal(qty), unit_price=price, vat_rate=item.vat_rate,
            account_code=item.account_code,
        )

    def _je(self, ref: str, day: date, desc: str,
            pairs: list[tuple[str, Decimal, Decimal]]) -> None:
        lines = []
        for code, debit, credit in pairs:
            account = self._accounts.find_by_code(code)
            lines.append(JournalLine(
                account_code=code,
                account_name=account.name if account else "",
                debit=debit, credit=credit,
            ))
        self._journal.create(JournalEntry(
            ref=ref, entry_date=day, description=desc,
            status=EntryStatus.POSTED, lines=lines,
        ))


def _last_day(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    from datetime import timedelta
    return date(year, month + 1, 1) - timedelta(days=1)


# Every table that holds business data an accountant enters or that the demo
# seeder writes. Deliberately excludes `account` (the TT133/TT200 chart of
# accounts, reloaded on every launch), `schema_version`, `settings` and
# `sqlite_sequence`. Keep this in sync with new migrations.
_DATA_TABLES = (
    "journal_line", "journal_entry",
    "invoice_line", "invoice",
    "inventory_movement", "fixed_asset",
    "material_sheet_line",
    "costing_product", "costing_sheet",
    "bom_line", "product_sheet_line",
    "book_closing", "opening_balance",
    "partner", "item",
)


def reset_data() -> None:
    """Wipe all business data, leaving a clean slate for real bookkeeping.

    Removes every demo/entered record (journal, invoices, inventory, worksheets,
    partners, items, …) but keeps the chart of accounts and the chosen circular
    (TT133/TT200), so the accountant opens the app with an empty ledger ready
    for real numbers. Idempotent and safe to run repeatedly.
    """
    init_database()
    conn = get_connection()
    with conn:
        for table in _DATA_TABLES:
            conn.execute(f"DELETE FROM {table}")
        # Reset AUTOINCREMENT counters so refs (BH0001, PN0001, …) restart at 1.
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN (%s)"
            % ",".join("?" for _ in _DATA_TABLES),
            _DATA_TABLES,
        )
    # Clear the demo flag but leave `active_circular` and other config untouched.
    SettingsRepository().set(_SEED_FLAG, "")


def _wipe() -> None:
    reset_data()


if __name__ == "__main__":
    import sys

    did = seed_demo(reset="--reset" in sys.argv)
    print("Seeded demo data." if did else "Demo data already present (use --reset).")
    # Note: prefer `python seed_demo.py` for UTF-8 friendly output.
