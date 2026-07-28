"""Ba pool chi phí của bảng giá thành lấy thẳng từ sổ cái (TK 1540x).

Kế toán ghi bút toán lương ``Nợ 15402 / Có 334`` ở Sổ nhật ký chung thì bảng
tính giá thành phải tự có tiền nhân công, không phải gõ lại lần nữa.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest


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
    from data.repositories.journal_repo import JournalRepository
    from domain.services.costing_pool_service import CostingPoolService
    from domain.services.journal_service import JournalService

    return CostingPoolService(JournalService(JournalRepository(conn)))


def _post(conn, ref, pairs, when=date(2026, 4, 30), status=None):
    """Ghi một bút toán; *pairs* là [(TK, nợ, có)]."""
    from data.repositories.journal_repo import JournalRepository
    from domain.models.journal import EntryStatus, JournalEntry, JournalLine
    from domain.services.journal_service import JournalService

    JournalService(JournalRepository(conn)).create(JournalEntry(
        ref=ref,
        entry_date=when,
        description="Tiền lương tháng 04",
        status=status or EntryStatus.POSTED,
        lines=[
            JournalLine(account_code=code,
                        debit=Decimal(str(debit)), credit=Decimal(str(credit)))
            for code, debit, credit in pairs
        ],
    ))


_APRIL = (date(2026, 4, 1), date(2026, 4, 30))


# ----- phân loại tài khoản → pool -------------------------------------------


def test_account_maps_to_the_right_pool():
    from domain.services.costing_pool_service import pool_of

    assert pool_of("15402") == "labor"
    assert pool_of("154032") == "overhead"
    assert pool_of("154033") == "other"
    # 15403 là TK cha (khấu hao máy SX hạch toán thẳng vào đây).
    assert pool_of("15403") == "overhead"
    # Không phải chi phí sản xuất → không vào pool nào.
    assert pool_of("15401") is None
    assert pool_of("334") is None
    assert pool_of("642") is None


def test_child_accounts_are_not_swallowed_by_the_parent():
    """'154032'.startswith('15403') là True — phải khớp mã cụ thể trước."""
    from domain.services.costing_pool_service import pool_of

    assert pool_of("154032") == "overhead"
    assert pool_of("154033") == "other"     # không bị gom vào 'overhead'


# ----- đọc từ sổ cái ---------------------------------------------------------


def test_wage_entry_fills_the_labor_pool(in_memory_db):
    """Ca chính: Nợ 15402 / Có 334 → pool nhân công."""
    svc = _service(in_memory_db)
    _post(in_memory_db, "KC01", [("15402", 50_000_000, 0), ("334", 0, 50_000_000)])

    pools = svc.pools_for(*_APRIL)
    assert pools.labor == Decimal("50000000")
    assert pools.overhead == Decimal("0")
    assert pools.other == Decimal("0")


def test_all_three_pools_are_collected(in_memory_db):
    svc = _service(in_memory_db)
    _post(in_memory_db, "KC01", [("15402", 50_000_000, 0), ("334", 0, 50_000_000)])
    _post(in_memory_db, "KC02", [("154032", 8_000_000, 0), ("331", 0, 8_000_000)])
    _post(in_memory_db, "KC03", [("154033", 2_000_000, 0), ("331", 0, 2_000_000)])

    pools = svc.pools_for(*_APRIL)
    assert pools.labor == Decimal("50000000")
    assert pools.overhead == Decimal("8000000")
    assert pools.other == Decimal("2000000")
    assert pools.total == Decimal("60000000")


def test_depreciation_on_parent_account_lands_in_overhead(in_memory_db):
    """Khấu hao máy SX ghi Nợ 15403 → pool SX chung."""
    svc = _service(in_memory_db)
    _post(in_memory_db, "KH01", [("15403", 12_000_000, 0), ("2141", 0, 12_000_000)])

    assert svc.pools_for(*_APRIL).overhead == Decimal("12000000")


def test_credit_reduces_the_pool(in_memory_db):
    """Bút toán hoàn nhập tự trừ ra, không phải sửa tay."""
    svc = _service(in_memory_db)
    _post(in_memory_db, "KC01", [("15402", 50_000_000, 0), ("334", 0, 50_000_000)])
    _post(in_memory_db, "DC01", [("334", 5_000_000, 0), ("15402", 0, 5_000_000)])

    assert svc.pools_for(*_APRIL).labor == Decimal("45000000")


def test_draft_entries_are_ignored(in_memory_db):
    from domain.models.journal import EntryStatus

    svc = _service(in_memory_db)
    _post(in_memory_db, "NH01", [("15402", 50_000_000, 0), ("334", 0, 50_000_000)],
          status=EntryStatus.DRAFT)

    assert svc.pools_for(*_APRIL).labor == Decimal("0")


def test_entries_outside_the_period_are_ignored(in_memory_db):
    svc = _service(in_memory_db)
    _post(in_memory_db, "KC01", [("15402", 50_000_000, 0), ("334", 0, 50_000_000)],
          when=date(2026, 5, 31))

    assert svc.pools_for(*_APRIL).labor == Decimal("0")
    assert svc.pools_for(date(2026, 5, 1),
                         date(2026, 5, 31)).labor == Decimal("50000000")


def test_material_account_is_not_a_pool(in_memory_db):
    """15401 (NVL) đã nằm ở cột riêng — không được gom vào pool nào."""
    svc = _service(in_memory_db)
    _post(in_memory_db, "NVL1", [("15401", 30_000_000, 0), ("152", 0, 30_000_000)])

    assert svc.pools_for(*_APRIL).total == Decimal("0")


# ----- bút toán kết chuyển của chính bảng giá thành --------------------------


def test_carryover_entry_does_not_drain_the_pool(in_memory_db):
    """``GT-155`` (Nợ 155 / Có 154032) là kết chuyển, không phải giảm chi phí.

    Đếm nó vào thì pool tự trừ đúng bằng số vừa phân bổ: lưu xong mở lại tab là
    ô SX chung nhảy sang số âm.
    """
    svc = _service(in_memory_db)
    _post(in_memory_db, "KC02", [("154032", 8_000_000, 0), ("331", 0, 8_000_000)])
    _post(in_memory_db, "GT-155/2026-04",
          [("155", 8_000_000, 0), ("154032", 0, 8_000_000)])

    assert svc.pools_for(*_APRIL).overhead == Decimal("8000000")


def test_carryover_alone_never_drives_the_pool_negative(in_memory_db):
    """Số gõ tay không có bút toán Nợ: kết chuyển không được kéo pool xuống âm."""
    svc = _service(in_memory_db)
    _post(in_memory_db, "GT-155/2026-04",
          [("155", 10_000_000, 0), ("154032", 0, 10_000_000)])

    assert svc.pools_for(*_APRIL).overhead == Decimal("0")


def test_material_carryover_entry_is_ignored(in_memory_db):
    """``GT-NVL`` chỉ chạm 15401/152 — vẫn loại cho nhất quán."""
    svc = _service(in_memory_db)
    _post(in_memory_db, "GT-NVL/2026-04",
          [("15401", 30_000_000, 0), ("152", 0, 30_000_000)])

    assert svc.pools_for(*_APRIL).total == Decimal("0")


def test_pool_is_stable_across_repeated_saves(in_memory_db):
    """Lưu đi lưu lại bảng giá thành thì pool phải giữ nguyên một con số."""
    svc = _service(in_memory_db)
    _post(in_memory_db, "KC02", [("154032", 8_000_000, 0), ("331", 0, 8_000_000)])

    first = svc.pools_for(*_APRIL).overhead
    for attempt in range(3):
        _post(in_memory_db, f"GT-155/2026-04-{attempt}",
              [("155", 8_000_000, 0), ("154032", 0, 8_000_000)])
        assert svc.pools_for(*_APRIL).overhead == first


# ----- khấu hao máy SX đã ghi sổ ---------------------------------------------


def test_posted_depreciation_is_reported(in_memory_db):
    """Nút "Lấy KH máy SX" cần biết khấu hao đã nằm sẵn trong pool hay chưa."""
    svc = _service(in_memory_db)
    _post(in_memory_db, "KH-202604",
          [("15403", 12_000_000, 0), ("2141", 0, 12_000_000)])

    assert svc.posted_production_depreciation(2026, 4) == Decimal("12000000")
    # Cả năm gộp mọi tháng.
    assert svc.posted_production_depreciation(2026) == Decimal("12000000")
    # Tháng khác chưa ghi khấu hao.
    assert svc.posted_production_depreciation(2026, 5) == Decimal("0")


def test_posted_depreciation_ignores_non_depreciation_entries(in_memory_db):
    """Tiền điện Nợ 154032 vẫn là chi phí SX chung, nhưng không phải khấu hao."""
    svc = _service(in_memory_db)
    _post(in_memory_db, "KC02", [("154032", 8_000_000, 0), ("331", 0, 8_000_000)])

    assert svc.posted_production_depreciation(2026, 4) == Decimal("0")


def test_posted_depreciation_ignores_non_production_assets(in_memory_db):
    """KH văn phòng (Nợ 642) không thuộc pool SX chung."""
    svc = _service(in_memory_db)
    _post(in_memory_db, "KH-202604",
          [("642", 5_000_000, 0), ("2141", 0, 5_000_000)])

    assert svc.posted_production_depreciation(2026, 4) == Decimal("0")


# ----- pool chảy vào giá thành ----------------------------------------------


def test_ledger_pool_is_allocated_into_product_cost(in_memory_db):
    """Lương ghi sổ → pool nhân công → phân bổ vào giá thành theo tỷ lệ NVL."""
    from domain.models.costing import CostingInput
    from domain.services.costing_service import CostingService

    svc = _service(in_memory_db)
    _post(in_memory_db, "KC01", [("15402", 60_000_000, 0), ("334", 0, 60_000_000)])
    pools = svc.pools_for(*_APRIL)

    sheet = CostingService().compute(
        [
            CostingInput(code="TP01", name="A", quantity=Decimal("10"),
                         material_cost=Decimal("30000000")),
            CostingInput(code="TP02", name="B", quantity=Decimal("10"),
                         material_cost=Decimal("10000000")),
        ],
        pools,
    )
    # Tỷ lệ NVL 3:1 → nhân công chia 45tr / 15tr.
    assert sheet.rows[0].labor_cost == Decimal("45000000")
    assert sheet.rows[1].labor_cost == Decimal("15000000")
    assert sheet.unallocated_pools == Decimal("0")
