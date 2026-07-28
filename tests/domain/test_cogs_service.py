"""Kết chuyển giá vốn cuối kỳ (KC-GV) — CogsService.

Trọng tâm: lương công nhân về trễ vẫn phải vào giá vốn. Vì vậy hóa đơn bán không
còn ghi 632 ngay lúc bán; cuối kỳ mới định giá bình quân **cuối kỳ** rồi kết
chuyển Nợ 632 / Có kho, đồng thời định giá lại bút toán xuất bán để sổ kho (NXT)
khớp sổ cái.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

OCT_FROM = date(2025, 10, 1)
OCT_TO = date(2025, 10, 31)
OCT_KEY = "2025-10"


@pytest.fixture
def in_memory_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.config.DB_PATH", db_file)
    monkeypatch.setattr("data.database.DB_PATH", db_file)

    import data.database as db_mod
    db_mod._conn = None
    db_mod.init_database()
    yield db_mod.get_connection()
    db_mod.close_connection()


def _services(conn):
    """(sales, inventory, journal, cogs) đều dùng chung kết nối test."""
    from data.repositories.account_repo import AccountRepository
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.invoice_repo import InvoiceRepository
    from data.repositories.item_repo import ItemRepository
    from data.repositories.journal_repo import JournalRepository
    from data.repositories.partner_repo import PartnerRepository
    from domain.services.cogs_service import CogsService
    from domain.services.inventory_service import InventoryService
    from domain.services.journal_service import JournalService
    from domain.services.sales_service import SalesService

    inventory = InventoryService(InventoryRepository(conn), ItemRepository(conn))
    journal = JournalService(JournalRepository(conn))
    sales = SalesService(
        InvoiceRepository(conn), inventory, journal,
        PartnerRepository(conn), AccountRepository(conn),
    )
    cogs = CogsService(
        journal, inventory=inventory, movements=InventoryRepository(conn),
        invoices=InvoiceRepository(conn), accounts=AccountRepository(conn),
    )
    return sales, inventory, journal, cogs


def _seed_product(conn, code="TP01", name="Bàn gỗ"):
    from data.repositories.item_repo import ItemRepository
    from domain.models.item import Item, ItemCategory

    ItemRepository(conn).insert(
        Item(code=code, name=name, category=ItemCategory.PRODUCT, unit="Cái")
    )


def _produce(conn, qty, unit_cost, code="TP01"):
    """Nhập kho 155 rồi để bảng giá thành định giá lại theo giá thành đơn vị.

    Số lượng do chứng từ nhập kho làm chủ (ở đây là Bảng kê TP, nguồn
    ``BK-TP:<kỳ>``); bảng giá thành chỉ đẩy *đơn giá* ngược về. Gọi lại với đơn
    giá khác = lương công nhân về trễ làm giá thành tăng: số lượng giữ nguyên,
    chỉ đơn giá đổi.
    """
    from datetime import datetime

    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from domain.models.inventory import InventoryMovement, MovementKind
    from domain.services.inventory_service import InventoryService
    from domain.services.material_issue_service import MaterialIssueService

    inventory = InventoryService(InventoryRepository(conn), ItemRepository(conn))
    source = f"BK-TP:{OCT_KEY}"
    inventory.replace_source_movements(source, [InventoryMovement(
        item_code=code, item_name="Bàn gỗ", account_code="155",
        move_date=date(2025, 10, 1), kind=MovementKind.IN,
        quantity=Decimal(qty), unit_cost=Decimal(unit_cost),
        source_ref=source, created_at=datetime.now(),
    )])
    issue = MaterialIssueService(inventory=inventory, item_repo=ItemRepository(conn))
    return issue.reprice_finished_goods(
        OCT_KEY, [(code, Decimal(qty), Decimal(unit_cost))]
    )


def _sell(sales, ref, qty, price="30000", code="TP01", when=date(2025, 10, 15)):
    from domain.models.invoice import Invoice, InvoiceLine, PaymentMethod

    sales.create(Invoice(
        ref=ref,
        invoice_date=when,
        payment_method=PaymentMethod.CREDIT,
        description="Bán thành phẩm",
        lines=[
            InvoiceLine(
                item_code=code, item_name="Bàn gỗ", unit="Cái",
                quantity=Decimal(qty), unit_price=Decimal(price),
                vat_rate=Decimal("10"), account_code="155",
            )
        ],
    ))


def _line(entry, account_code):
    return next(l for l in entry.lines if l.account_code == account_code)


# ----- hóa đơn bán không còn ghi 632 ----------------------------------------


def test_sales_invoice_no_longer_posts_632(in_memory_db):
    """Hóa đơn bán chỉ ghi doanh thu; kho vẫn giảm số lượng."""
    sales, inventory, journal, _cogs = _services(in_memory_db)
    _seed_product(in_memory_db)
    _produce(in_memory_db, "100", "10000")

    _sell(sales, "HD001", "40")

    entry = journal.find_by_ref("HD001")
    assert entry is not None and entry.is_balanced
    assert {l.account_code for l in entry.lines} == {"131", "511", "3331"}
    # Kho vẫn xuất đủ 40 cái.
    assert inventory.on_hand("TP01") == Decimal("60")


# ----- CA CHÍNH: lương về trễ vẫn vào giá vốn -------------------------------


def test_late_wages_are_included_in_period_end_cogs(in_memory_db):
    """Lương về sau khi đã bán vẫn phải nằm trong giá vốn kỳ đó.

    1. giá thành CHƯA có lương → nhập 155 giá thấp (10.000/cái)
    2. bán 40 cái (bút toán xuất kho chốt tạm ở 10.000)
    3. lương 15402 về → giá thành 12.000/cái, GT-TP thay giá nhập 155
    4. kết chuyển cuối kỳ → 632 = 40 × 12.000, KHÔNG phải 40 × 10.000
    """
    sales, _inventory, journal, cogs = _services(in_memory_db)
    _seed_product(in_memory_db)

    _produce(in_memory_db, "100", "10000")      # chưa có lương
    _sell(sales, "HD001", "40")
    _produce(in_memory_db, "100", "12000")      # lương về → giá thành tăng

    entry = cogs.post(OCT_FROM, OCT_TO)

    assert entry is not None and entry.ref == "KC-GV/2025-10"
    assert entry.is_balanced
    assert _line(entry, "632").debit == Decimal("480000")   # 40 × 12.000
    assert _line(entry, "155").credit == Decimal("480000")
    # Bút toán bán hàng vẫn không có 632 — giá vốn chỉ nằm ở KC-GV.
    assert all(l.account_code != "632" for l in journal.find_by_ref("HD001").lines)


# ----- sổ kho khớp sổ cái ----------------------------------------------------


def test_cogs_keeps_nxt_and_ledger_in_agreement(in_memory_db):
    """Xuất·TT của NXT (155) == số tiền ghi Có 155 trong KC-GV."""
    sales, inventory, _journal, cogs = _services(in_memory_db)
    _seed_product(in_memory_db)

    _produce(in_memory_db, "100", "10000")
    _sell(sales, "HD001", "40")
    _produce(in_memory_db, "100", "12000")

    entry = cogs.post(OCT_FROM, OCT_TO)

    row = next(r for r in inventory.compute_nxt(OCT_FROM, OCT_TO)
               if r.item_code == "TP01")
    assert row.out_value == _line(entry, "155").credit   # 480.000
    # Tồn cuối kỳ = 60 cái × 12.000 — khớp số dư TK 155 sau khi ghi Có 480.000.
    assert row.closing_qty == Decimal("60")
    assert row.closing_value == Decimal("720000")
    assert row.in_value - _line(entry, "155").credit == row.closing_value


def test_reprice_updates_stored_cost_of_sale_movements(in_memory_db):
    """reprice ghi lại đơn giá trên chính bút toán xuất bán (không cộng dồn)."""
    from data.repositories.inventory_repo import InventoryRepository

    sales, _inventory, _journal, cogs = _services(in_memory_db)
    _seed_product(in_memory_db)

    _produce(in_memory_db, "100", "10000")
    _sell(sales, "HD001", "40")
    _produce(in_memory_db, "100", "12000")

    out = next(m for m in InventoryRepository(in_memory_db).list_all()
               if m.source_ref == "HD001")
    assert out.unit_cost == Decimal("10000")        # giá chốt tạm lúc bán

    assert cogs.reprice(OCT_FROM, OCT_TO) == 1
    out = next(m for m in InventoryRepository(in_memory_db).list_all()
               if m.source_ref == "HD001")
    assert out.unit_cost == Decimal("12000")
    # Chạy lại không đổi gì nữa.
    assert cogs.reprice(OCT_FROM, OCT_TO) == 0


# ----- idempotent ------------------------------------------------------------


def test_cogs_post_is_idempotent(in_memory_db):
    """post 2 lần → vẫn 1 bút toán KC-GV, 632 không cộng dồn."""
    sales, _inventory, journal, cogs = _services(in_memory_db)
    _seed_product(in_memory_db)

    _produce(in_memory_db, "100", "12000")
    _sell(sales, "HD001", "40")

    first = cogs.post(OCT_FROM, OCT_TO)
    second = cogs.post(OCT_FROM, OCT_TO)

    assert first is not None and second is not None
    refs = [e.ref for e in journal.list_all() if e.ref.startswith("KC-GV/")]
    assert refs == ["KC-GV/2025-10"]
    assert _line(second, "632").debit == Decimal("480000")
    assert cogs.is_posted(OCT_FROM, OCT_TO)

    cogs.unpost(OCT_FROM, OCT_TO)
    assert not cogs.is_posted(OCT_FROM, OCT_TO)


# ----- nối vào kết chuyển 911 ------------------------------------------------


def test_result_transfers_cogs_to_911(in_memory_db):
    """ResultService.post sinh KC-GV rồi KC-CP đưa đúng 632 sang 911."""
    from data.repositories.account_repo import AccountRepository
    from domain.services.result_service import ResultService

    sales, _inventory, journal, cogs = _services(in_memory_db)
    _seed_product(in_memory_db)

    _produce(in_memory_db, "100", "12000")
    _sell(sales, "HD001", "40")

    results = ResultService(journal, AccountRepository(in_memory_db), cogs=cogs)
    created = results.post(OCT_FROM, OCT_TO)

    refs = [e.ref for e in created]
    assert refs[0] == "KC-GV/2025-10"          # giá vốn chạy trước
    assert "KC-CP/2025-10" in refs

    kc_gv = journal.find_by_ref("KC-GV/2025-10")
    kc_cp = journal.find_by_ref("KC-CP/2025-10")
    # 632 phát sinh ở KC-GV được KC-CP kết chuyển trọn sang 911.
    assert _line(kc_cp, "632").credit == _line(kc_gv, "632").debit == Decimal("480000")
    assert results.is_posted(OCT_FROM, OCT_TO)


def test_result_unpost_removes_cogs_entry_too(in_memory_db):
    from data.repositories.account_repo import AccountRepository
    from domain.services.result_service import ResultService

    sales, _inventory, journal, cogs = _services(in_memory_db)
    _seed_product(in_memory_db)
    _produce(in_memory_db, "100", "12000")
    _sell(sales, "HD001", "40")

    results = ResultService(journal, AccountRepository(in_memory_db), cogs=cogs)
    results.post(OCT_FROM, OCT_TO)
    results.unpost(OCT_FROM, OCT_TO)

    assert journal.find_by_ref("KC-GV/2025-10") is None
    assert not results.is_posted(OCT_FROM, OCT_TO)


# ----- chốt sổ ---------------------------------------------------------------


def test_closed_year_blocks_post_before_touching_stock(in_memory_db):
    """Năm đã chốt: từ chối NGAY, sổ kho không được định giá lại nửa chừng."""
    from data.repositories.inventory_repo import InventoryRepository
    from domain.services.closing_service import ClosingError, ClosingService

    sales, _inventory, journal, cogs = _services(in_memory_db)
    _seed_product(in_memory_db)
    _produce(in_memory_db, "100", "10000")
    _sell(sales, "HD001", "40")
    _produce(in_memory_db, "100", "12000")

    ClosingService().close_year(2025)

    with pytest.raises(ClosingError):
        cogs.post(OCT_FROM, OCT_TO)

    # Đơn giá trên bút toán xuất bán giữ nguyên — chưa bị ghi đè.
    out = next(m for m in InventoryRepository(in_memory_db).list_all()
               if m.source_ref == "HD001")
    assert out.unit_cost == Decimal("10000")
    assert journal.find_by_ref("KC-GV/2025-10") is None


# ----- bán khi kỳ chưa thấy nhập --------------------------------------------


def test_cogs_falls_back_to_stored_cost_when_no_stock(in_memory_db):
    """Kỳ bán không có tồn đầu lẫn nhập → giữ đơn giá đã ghi, không để về 0.

    Xảy ra khi hàng nhập kho được ghi sổ với ngày SAU kỳ bán (nhập trễ): NXT của
    kỳ chưa thấy đồng nhập nào nên không tính được bình quân cuối kỳ.
    """
    sales, inventory, _journal, cogs = _services(in_memory_db)
    _seed_product(in_memory_db)
    # Nhập kho ghi ngày 5/11 — sau kỳ tháng 10.
    inventory.record_in("TP01", Decimal("100"), Decimal("7000"),
                        move_date=date(2025, 11, 5))
    _sell(sales, "HD001", "10")   # bán 15/10, đơn giá chốt 7.000 từ sổ kho

    assert cogs.unit_costs(OCT_FROM, OCT_TO).get("TP01") is None
    entry = cogs.post(OCT_FROM, OCT_TO)

    assert entry is not None
    assert _line(entry, "632").debit == Decimal("70000")   # 10 × 7.000, không phải 0
