"""Bảng kê của kỳ rộng gộp số liệu từ bảng kê kỳ con.

Quý = ba tháng, năm = bốn quý. Quy tắc gộp: tồn ĐẦU KỲ lấy của kỳ con sớm nhất
có mã đó (đầu kỳ tháng 05 vốn đã là cuối kỳ tháng 04 — cộng dồn là nhân đôi),
nhập / xuất thì cộng dồn. Dòng gộp là chỉ đọc: sửa phải vào đúng bảng tháng, và
lưu lại bảng quý không được ghi đè hay đẩy sổ kho lần nữa.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.models.material_sheet import MaterialLine, MaterialSheet
from domain.models.product_sheet import ProductLine, ProductSheet
from domain.services.period_tag import child_period_keys


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


def _material_service(conn):
    from data.repositories.material_sheet_repo import MaterialSheetRepository
    from domain.services.material_sheet_service import MaterialSheetService

    return MaterialSheetService(MaterialSheetRepository(conn))


def _product_service(conn):
    from data.repositories.costing_repo import CostingRepository
    from data.repositories.product_sheet_repo import ProductSheetRepository
    from domain.services.costing_service import CostingService
    from domain.services.product_sheet_service import ProductSheetService

    return ProductSheetService(
        ProductSheetRepository(conn),
        costing=CostingService(CostingRepository(conn)),
    )


def _mat(**kw) -> MaterialLine:
    defaults = dict(code="S20", name="Sắt cây 20", unit="Kg")
    defaults.update(kw)
    return MaterialLine(**{k: (Decimal(str(v)) if isinstance(v, (int, float)) else v)
                           for k, v in defaults.items()})


def _prod(**kw) -> ProductLine:
    defaults = dict(code="TP01", name="Bàn gỗ", unit="Cái")
    defaults.update(kw)
    return ProductLine(**{k: (Decimal(str(v)) if isinstance(v, (int, float)) else v)
                          for k, v in defaults.items()})


def _save_three_months(svc, sheet_cls, make_line):
    """Ba tháng của quý 2, tháng sau nối tiếp tồn cuối của tháng trước.

    Mọi thứ đồng giá 10.000 đ/đơn vị để bảng kê thành phẩm (vốn tự tính ĐG xuất
    bình quân gia quyền lúc lưu) ra đúng số tròn — nhờ vậy hai bảng dùng chung
    được bộ số liệu này và phép cộng kiểm chứng được bằng tay.
    """
    months = (
        ("2026-04", dict(opening_qty=100, opening_value=1_000_000,
                         in_qty=50, in_value=500_000,
                         out_qty=30, out_value=300_000)),      # cuối kỳ 120
        ("2026-05", dict(opening_qty=120, opening_value=1_200_000,
                         in_qty=20, in_value=200_000,
                         out_qty=10, out_value=100_000)),      # cuối kỳ 130
        ("2026-06", dict(opening_qty=130, opening_value=1_300_000,
                         in_qty=0, in_value=0,
                         out_qty=5, out_value=50_000)),        # cuối kỳ 125
    )
    for key, values in months:
        svc.save(sheet_cls(period_key=key, lines=[make_line(**values)]))


# ----- kỳ con ---------------------------------------------------------------


def test_child_period_keys_walks_one_level_down():
    assert child_period_keys("2026") == [f"2026-Q{q}" for q in range(1, 5)]
    assert child_period_keys("2026-Q2") == ["2026-04", "2026-05", "2026-06"]
    assert child_period_keys("2026-06") == []


# ----- bảng kê NVL ----------------------------------------------------------


def test_quarter_sheet_sums_the_three_monthly_sheets(in_memory_db):
    svc = _material_service(in_memory_db)
    _save_three_months(svc, MaterialSheet, _mat)

    line = next(ln for ln in svc.load("2026-Q2").lines if ln.code == "S20")

    assert line.opening_qty == Decimal("100")        # của tháng 04, không cộng dồn
    assert line.opening_value == Decimal("1000000")
    assert line.in_qty == Decimal("70")              # 50 + 20 + 0
    assert line.in_value == Decimal("700000")
    assert line.out_qty == Decimal("45")             # 30 + 10 + 5
    assert line.out_value == Decimal("450000")
    # Khớp tồn cuối kỳ của tháng cuối cùng: 100 + 70 − 45 = 125.
    assert line.closing_qty == Decimal("125")
    assert line.closing_value == Decimal("1250000")


def test_year_sheet_rolls_up_through_the_quarters(in_memory_db):
    svc = _material_service(in_memory_db)
    _save_three_months(svc, MaterialSheet, _mat)

    line = next(ln for ln in svc.load("2026").lines if ln.code == "S20")

    assert line.in_qty == Decimal("70")
    assert line.closing_qty == Decimal("125")


def test_rolled_up_rows_are_read_only(in_memory_db):
    svc = _material_service(in_memory_db)
    _save_three_months(svc, MaterialSheet, _mat)

    quarter = svc.load("2026-Q2")

    assert all(ln.from_ledger for ln in quarter.lines)
    assert svc.validate(quarter) == []      # bảng quý không sở hữu dòng nào


def test_saving_the_quarter_does_not_duplicate_the_monthly_rows(in_memory_db):
    """Lưu lại bảng quý không được ghi đè kỳ con hay đẩy sổ kho lần nữa."""
    from data.repositories.material_sheet_repo import MaterialSheetRepository

    svc = _material_service(in_memory_db)
    _save_three_months(svc, MaterialSheet, _mat)
    repo = MaterialSheetRepository(in_memory_db)

    svc.save(svc.load("2026-Q2"))

    assert repo.list_for_period("2026-Q2") == []          # không nhân bản
    assert len(repo.list_for_period("2026-04")) == 1      # tháng còn nguyên
    line = next(ln for ln in svc.load("2026-Q2").lines if ln.code == "S20")
    assert line.in_qty == Decimal("70")                   # vẫn đúng, không gấp đôi


def test_a_row_declared_on_the_quarter_wins_over_its_months(in_memory_db):
    svc = _material_service(in_memory_db)
    _save_three_months(svc, MaterialSheet, _mat)

    svc.save(MaterialSheet(period_key="2026-Q2", lines=[
        _mat(opening_qty=1, opening_value=10, in_qty=2, in_value=20),
    ]))

    lines = [ln for ln in svc.load("2026-Q2").lines if ln.code == "S20"]
    assert len(lines) == 1                      # không vừa gộp vừa khai riêng
    assert lines[0].in_qty == Decimal("2")      # số khai ở kỳ quý thắng


def test_a_material_appearing_only_later_keeps_its_own_opening(in_memory_db):
    """NVL chỉ có ở tháng 06 thì đầu kỳ quý là đầu kỳ tháng 06 của nó."""
    svc = _material_service(in_memory_db)
    svc.save(MaterialSheet(period_key="2026-06", lines=[
        _mat(code="S30", name="Sắt cây 30",
             opening_qty=7, opening_value=70, in_qty=3, in_value=30),
    ]))

    line = next(ln for ln in svc.load("2026-Q2").lines if ln.code == "S30")

    assert line.opening_qty == Decimal("7")
    assert line.closing_qty == Decimal("10")


# ----- bảng kê thành phẩm ---------------------------------------------------


def test_product_quarter_sheet_sums_the_three_monthly_sheets(in_memory_db):
    svc = _product_service(in_memory_db)
    _save_three_months(svc, ProductSheet, _prod)

    line = next(ln for ln in svc.load("2026-Q2").lines if ln.code == "TP01")

    assert line.opening_qty == Decimal("100")
    assert line.in_qty == Decimal("70")
    assert line.out_qty == Decimal("45")
    # TT xuất là TỔNG của ba tháng (300k + 100k + 50k), không tính lại bình quân
    # cả quý — nếu tính lại sẽ lệch với số đã ghi sổ từng tháng.
    assert line.out_value == Decimal("450000")
    assert line.closing_qty == Decimal("125")
    assert line.closing_value == Decimal("1250000")


def test_product_quarter_feeds_costing_quantities(in_memory_db):
    """Số lượng sản xuất của bảng giá thành quý = tổng SL nhập ba tháng."""
    svc = _product_service(in_memory_db)
    _save_three_months(svc, ProductSheet, _prod)

    quantities = dict(
        (code, qty) for code, _name, qty in svc.input_quantities("2026-Q2")
    )

    assert quantities["TP01"] == Decimal("70")


def test_next_quarter_opening_carries_from_the_rolled_up_quarter(in_memory_db):
    """Tồn đầu quý 3 = tồn cuối quý 2 đã gộp, không phải số của riêng kỳ quý."""
    svc = _product_service(in_memory_db)
    _save_three_months(svc, ProductSheet, _prod)

    carried = svc.carry_forward_lines("2026-Q3")

    line = next(ln for ln in carried if ln.code == "TP01")
    assert line.opening_qty == Decimal("125")
    assert line.opening_value == Decimal("1250000")
