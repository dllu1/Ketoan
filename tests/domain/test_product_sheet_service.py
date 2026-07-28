"""Tests for the finished-goods NXT worksheet (Bảng kê N–X–T thành phẩm, 155).

Covers the derivation rules from the handwritten form notes: ĐG xuất bình quân
gia quyền, TT nhập lấy từ giá thành (apply_costing), tồn đầu kỳ chuyển từ tồn
cuối kỳ trước (carry-forward), and the negative-closing save guard.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.models.product_sheet import ProductLine, ProductSheet


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


def _service(conn):
    from data.repositories.costing_repo import CostingRepository
    from data.repositories.product_sheet_repo import ProductSheetRepository
    from domain.services.costing_service import CostingService
    from domain.services.product_sheet_service import ProductSheetService

    return ProductSheetService(
        ProductSheetRepository(conn),
        costing=CostingService(CostingRepository(conn)),
    )


def _line(**kw) -> ProductLine:
    defaults = dict(code="TP01", name="Bàn gỗ", unit="Cái")
    defaults.update(kw)
    return ProductLine(**{k: (Decimal(str(v)) if isinstance(v, (int, float)) else v)
                          for k, v in defaults.items()})


# ----- pure model: weighted-average derivation ------------------------------


def test_out_price_is_weighted_average_of_opening_plus_in():
    # ĐG xuất = (TT đầu + TT nhập) / (SL đầu + SL nhập)
    #         = (1.000.000 + 2.600.000) / (10 + 20) = 120.000
    line = _line(
        opening_qty=10, opening_value=1_000_000,
        in_qty=20, in_value=2_600_000,
        out_qty=15,
    )
    line.recompute()
    assert line.in_price == Decimal("130000")      # 2.600.000 / 20
    assert line.out_price == Decimal("120000")
    assert line.out_value == Decimal("1800000")    # 15 × 120.000
    assert line.closing_qty == Decimal("15")
    assert line.closing_value == Decimal("1800000")
    assert line.closing_price == Decimal("120000")


def test_full_issue_moves_entire_value_despite_rounding():
    # SL xuất = SL đầu + SL nhập → TT xuất = toàn bộ giá trị, tồn cuối 0/0
    # (1.000.000 / 3 would round; the rule prevents stranded đồng).
    line = _line(opening_qty=3, opening_value=1_000_000, out_qty=3)
    line.recompute()
    assert line.out_value == Decimal("1000000")
    assert line.closing_qty == Decimal("0")
    assert line.closing_value == Decimal("0")


def test_negative_closing_is_flagged():
    line = _line(opening_qty=10, opening_value=100_000, out_qty=15)
    line.recompute()
    assert line.is_negative


# ----- service: save guard + round trip -------------------------------------


def test_save_rejects_negative_closing(in_memory_db):
    from domain.services.product_sheet_service import ProductSheetError

    svc = _service(in_memory_db)
    sheet = ProductSheet(
        period_key="2026-06",
        lines=[_line(opening_qty=10, opening_value=100_000, out_qty=15)],
    )
    with pytest.raises(ProductSheetError):
        svc.save(sheet)
    assert svc.load("2026-06").lines == []


def test_save_then_load_round_trip_derives_columns(in_memory_db):
    svc = _service(in_memory_db)
    sheet = ProductSheet(
        period_key="2026-06",
        lines=[_line(opening_qty=10, opening_value=1_000_000,
                     in_qty=20, in_value=2_600_000, out_qty=15)],
    )
    svc.save(sheet)
    loaded = svc.load("2026-06")
    assert len(loaded.lines) == 1
    ln = loaded.lines[0]
    assert not ln.from_ledger            # manual row stays editable
    assert ln.out_price == Decimal("120000")
    assert ln.closing_qty == Decimal("15")
    assert ln.closing_value == Decimal("1800000")


def test_saved_sheet_appears_in_ledger_nxt(in_memory_db):
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from datetime import date
    from domain.services.inventory_service import InventoryService

    svc = _service(in_memory_db)
    svc.save(ProductSheet(
        period_key="2026-06",
        lines=[_line(opening_qty=10, opening_value=1_000_000,
                     in_qty=20, in_value=2_600_000, out_qty=15)],
    ))
    inv = InventoryService(InventoryRepository(in_memory_db),
                           ItemRepository(in_memory_db))
    rows = {r.item_code: r for r in inv.compute_nxt(date(2026, 6, 1),
                                                    date(2026, 6, 30))}
    assert rows["TP01"].opening_qty == Decimal("10")
    assert rows["TP01"].in_value == Decimal("2600000")
    assert rows["TP01"].closing_qty == Decimal("15")


# ----- carry-forward: tồn đầu kỳ = tồn cuối kỳ trước -------------------------


def test_opening_carries_forward_from_previous_month(in_memory_db):
    svc = _service(in_memory_db)
    svc.save(ProductSheet(
        period_key="2026-06",
        lines=[_line(opening_qty=10, opening_value=1_000_000,
                     in_qty=20, in_value=2_600_000, out_qty=15)],
    ))
    july = svc.load("2026-07")
    assert len(july.lines) == 1
    ln = july.lines[0]
    assert ln.code == "TP01"
    assert ln.opening_qty == Decimal("15")           # tồn cuối tháng 6
    assert ln.opening_value == Decimal("1800000")
    assert ln.opening_price == Decimal("120000")
    assert ln.in_qty == Decimal("0") and ln.out_qty == Decimal("0")


def test_saved_period_is_not_overwritten_by_carry_forward(in_memory_db):
    svc = _service(in_memory_db)
    svc.save(ProductSheet(
        period_key="2026-06",
        lines=[_line(opening_qty=10, opening_value=1_000_000)],
    ))
    svc.save(ProductSheet(
        period_key="2026-07",
        lines=[_line(code="TP02", name="Ghế gỗ", opening_qty=5,
                     opening_value=250_000)],
    ))
    july = svc.load("2026-07")
    assert [ln.code for ln in july.lines] == ["TP02"]


# ----- costing pull: TT nhập lấy từ giá thành --------------------------------


def _save_costing(conn, period_key: str) -> None:
    """Synthetic costing sheet: 10 cái TP01, NVL 1.000.000 + NC 200.000."""
    from data.repositories.costing_repo import CostingRepository
    from domain.models.costing import CostingInput, CostPools

    CostingRepository(conn).replace(
        period_key,
        CostPools(labor=Decimal("200000")),
        [CostingInput(code="TP01", name="Bàn gỗ", quantity=Decimal("10"),
                      material_cost=Decimal("1000000"))],
    )


def test_apply_costing_fills_in_qty_and_value(in_memory_db):
    svc = _service(in_memory_db)
    _save_costing(in_memory_db, "2026-06")

    sheet = ProductSheet(period_key="2026-06", lines=[])
    applied = svc.apply_costing(sheet)

    assert applied == 1
    ln = sheet.lines[0]
    assert ln.code == "TP01"
    assert ln.in_qty == Decimal("10")
    # Tổng giá thành = NVL 1.000.000 + NC (phân bổ hết cho SP duy nhất) 200.000
    assert ln.in_value == Decimal("1200000")
    assert ln.in_price == Decimal("120000")


def test_apply_costing_updates_existing_row_and_keeps_opening(in_memory_db):
    svc = _service(in_memory_db)
    _save_costing(in_memory_db, "2026-06")

    sheet = ProductSheet(
        period_key="2026-06",
        lines=[_line(opening_qty=4, opening_value=400_000)],
    )
    assert svc.apply_costing(sheet) == 1
    ln = sheet.lines[0]
    assert ln.opening_qty == Decimal("4")            # untouched
    assert ln.in_value == Decimal("1200000")
    # ĐG xuất bình quân = (400.000 + 1.200.000) / (4 + 10)
    assert ln.out_price == Decimal("114286")


# ----- feed costing: SL nhập 155 → số lượng sản xuất ------------------------


def test_input_quantities_returns_saved_in_qty(in_memory_db):
    svc = _service(in_memory_db)
    svc.save(ProductSheet(
        period_key="2026-06",
        lines=[
            _line(code="TP01", name="Bàn gỗ", in_qty=20, in_value=2_600_000),
            _line(code="TP02", name="Ghế gỗ", in_qty=5, in_value=500_000),
        ],
    ))
    assert svc.input_quantities("2026-06") == [
        ("TP01", "Bàn gỗ", Decimal("20")),
        ("TP02", "Ghế gỗ", Decimal("5")),
    ]


def test_input_quantities_skips_rows_without_in_qty(in_memory_db):
    # Dòng chỉ có tồn đầu (không nhập) không phải sản xuất trong kỳ → bỏ qua.
    svc = _service(in_memory_db)
    svc.save(ProductSheet(
        period_key="2026-06",
        lines=[
            _line(code="TP01", name="Bàn gỗ", opening_qty=10, opening_value=1_000_000),
            _line(code="TP02", name="Ghế gỗ", in_qty=5, in_value=500_000),
        ],
    ))
    assert svc.input_quantities("2026-06") == [("TP02", "Ghế gỗ", Decimal("5"))]


def test_input_quantities_sees_real_stock_in_documents(in_memory_db):
    """Thành phẩm nhập kho bằng chứng từ thật cũng phải kéo sang bảng giá thành.

    Trước đây chỉ đọc dòng nhập tay đã lưu, nên nhập kho qua nút "Nhập kho" thì
    bảng Giá thành SP trống trơn.
    """
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from datetime import date
    from decimal import Decimal as D
    from domain.services.inventory_service import InventoryService

    inv = InventoryService(InventoryRepository(in_memory_db),
                           ItemRepository(in_memory_db))
    inv.record_in("TP09", D("12"), D("50000"), move_date=date(2026, 6, 10),
                  account_code="155", item_name="Bàn sắt")

    svc = _service(in_memory_db)
    assert svc.input_quantities("2026-06") == [("TP09", "Bàn sắt", Decimal("12"))]


def test_costing_reprice_never_creates_quantity(in_memory_db):
    """Bảng giá thành chỉ đẩy ĐƠN GIÁ — không sinh ra lượng nhập 155 nào.

    Nếu nó tạo bút toán nhập riêng thì SL sản xuất bị cộng đôi mỗi lần lưu.
    """
    from data.repositories.inventory_repo import InventoryRepository
    from data.repositories.item_repo import ItemRepository
    from decimal import Decimal as D
    from domain.services.bom_service import BomService
    from domain.services.inventory_service import InventoryService
    from domain.services.material_issue_service import MaterialIssueService

    inv = InventoryService(InventoryRepository(in_memory_db),
                           ItemRepository(in_memory_db))
    issue = MaterialIssueService(inventory=inv,
                                 bom=BomService(inventory=inv),
                                 item_repo=ItemRepository(in_memory_db))
    issue.reprice_finished_goods("2026-06", [("TP01", D("20"), D("130000"))])

    svc = _service(in_memory_db)
    assert svc.input_quantities("2026-06") == []


def test_input_quantities_aggregates_duplicate_codes(in_memory_db):
    svc = _service(in_memory_db)
    svc.save(ProductSheet(
        period_key="2026-06",
        lines=[
            _line(code="TP01", name="Bàn gỗ", in_qty=20, in_value=2_600_000),
            _line(code="TP01", name="Bàn gỗ", in_qty=5, in_value=650_000),
        ],
    ))
    assert svc.input_quantities("2026-06") == [("TP01", "Bàn gỗ", Decimal("25"))]


# ----- giá thành → Nhập·ĐG (chiều ngược) ------------------------------------


def test_apply_costing_prices_writes_unit_cost_into_in_price(in_memory_db):
    """Giá thành đơn vị vừa tính chảy về cột Nhập·ĐG, giữ nguyên Nhập·SL."""
    svc = _service(in_memory_db)
    _save_costing(in_memory_db, "2026-06")     # 10 cái, tổng giá thành 1.200.000

    sheet = ProductSheet(period_key="2026-06", lines=[_line(in_qty=10)])
    assert svc.apply_costing_prices(sheet) == 1

    ln = sheet.lines[0]
    assert ln.in_qty == Decimal("10")           # SL vẫn do bảng kê làm chủ
    assert ln.in_price == Decimal("120000")     # = giá thành đơn vị
    assert ln.in_value == Decimal("1200000")


def test_apply_costing_prices_keeps_sheet_quantity(in_memory_db):
    """SL của bảng kê thắng: giá thành chỉ cấp đơn giá, không cấp số lượng."""
    svc = _service(in_memory_db)
    _save_costing(in_memory_db, "2026-06")      # bảng giá thành ghi SL = 10

    sheet = ProductSheet(period_key="2026-06", lines=[_line(in_qty=7)])
    svc.apply_costing_prices(sheet)

    ln = sheet.lines[0]
    assert ln.in_qty == Decimal("7")            # không bị kéo về 10
    assert ln.in_value == Decimal("840000")     # 7 × 120.000


def test_apply_costing_prices_is_idempotent(in_memory_db):
    """Chạy lại không đổi gì nữa — mỗi cột chỉ có một chiều nên không lặp."""
    svc = _service(in_memory_db)
    _save_costing(in_memory_db, "2026-06")

    sheet = ProductSheet(period_key="2026-06", lines=[_line(in_qty=10)])
    assert svc.apply_costing_prices(sheet) == 1
    assert svc.apply_costing_prices(sheet) == 0
    assert sheet.lines[0].in_value == Decimal("1200000")


def test_apply_costing_prices_skips_ledger_rows(in_memory_db):
    """Dòng sổ kho đã mang đơn giá của chứng từ — không được ghi đè."""
    svc = _service(in_memory_db)
    _save_costing(in_memory_db, "2026-06")

    ledger = _line(in_qty=10, in_value=999_000)
    ledger.from_ledger = True
    sheet = ProductSheet(period_key="2026-06", lines=[ledger])

    assert svc.apply_costing_prices(sheet) == 0
    assert sheet.lines[0].in_value == Decimal("999000")


def test_apply_costing_prices_leaves_products_without_costing_alone(in_memory_db):
    svc = _service(in_memory_db)
    _save_costing(in_memory_db, "2026-06")      # chỉ có TP01

    other = _line(code="TP99", name="Chưa tính giá thành", in_qty=5, in_value=500_000)
    sheet = ProductSheet(period_key="2026-06", lines=[other])

    assert svc.apply_costing_prices(sheet) == 0
    assert sheet.lines[0].in_value == Decimal("500000")


def test_round_trip_quantity_out_price_back(in_memory_db):
    """Vòng khép kín: Nhập·SL → SL giá thành → giá thành đơn vị → Nhập·ĐG."""
    from data.repositories.costing_repo import CostingRepository
    from domain.models.costing import CostingInput, CostPools

    svc = _service(in_memory_db)
    # 1. Kế toán gõ SL nhập vào bảng kê TP.
    svc.save(ProductSheet(period_key="2026-06", lines=[_line(in_qty=10)]))

    # 2. Bảng giá thành lấy đúng SL đó.
    assert svc.input_quantities("2026-06") == [("TP01", "Bàn gỗ", Decimal("10"))]

    # 3. Kế toán nhập chi phí bên bảng giá thành (NVL 1.000.000 + NC 200.000).
    CostingRepository(in_memory_db).replace(
        "2026-06", CostPools(labor=Decimal("200000")),
        [CostingInput(code="TP01", name="Bàn gỗ", quantity=Decimal("10"),
                      material_cost=Decimal("1000000"))],
    )

    # 4. Giá thành đơn vị quay lại cột Nhập·ĐG của bảng kê.
    sheet = svc.load("2026-06")
    svc.apply_costing_prices(sheet)
    ln = next(x for x in sheet.lines if x.code == "TP01" and not x.from_ledger)
    assert ln.in_qty == Decimal("10")
    assert ln.in_price == Decimal("120000")
