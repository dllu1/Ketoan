"""FixedAssetService tests — straight-line depreciation + monthly posting."""
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
    from data.repositories.account_repo import AccountRepository
    from data.repositories.fixed_asset_repo import FixedAssetRepository
    from data.repositories.journal_repo import JournalRepository
    from domain.services.fixed_asset_service import FixedAssetService
    from domain.services.journal_service import JournalService

    journal = JournalService(JournalRepository(conn))
    return FixedAssetService(FixedAssetRepository(conn), journal, AccountRepository(conn)), journal


def _asset(code="TS001", life=12, cost="120000000", start=date(2026, 1, 1)):
    from domain.models.fixed_asset import FixedAsset

    return FixedAsset(
        code=code, name="Máy CNC", asset_account="211", expense_account="642",
        cost=Decimal(cost), useful_life_months=life, start_date=start,
    )


def test_monthly_depreciation_straight_line(in_memory_db):
    svc, _ = _service(in_memory_db)
    asset = _asset()  # 120,000,000 / 12 = 10,000,000/tháng
    assert asset.monthly_depreciation == Decimal("10000000")


def test_accumulated_and_book_value(in_memory_db):
    svc, _ = _service(in_memory_db)
    asset = _asset()
    # Đến hết tháng 6/2026 = 6 kỳ.
    assert asset.accumulated_through(2026, 6) == Decimal("60000000")
    assert asset.book_value_through(2026, 6) == Decimal("60000000")
    # Hết đời (tháng 12) = khấu hao toàn bộ.
    assert asset.accumulated_through(2026, 12) == Decimal("120000000")
    assert asset.book_value_through(2026, 12) == Decimal("0")


def test_depreciation_before_start_is_zero(in_memory_db):
    svc, _ = _service(in_memory_db)
    asset = _asset(start=date(2026, 3, 1))
    assert asset.depreciation_for(2026, 2) == Decimal("0")
    assert asset.depreciation_for(2026, 3) == Decimal("10000000")


def test_post_monthly_depreciation_creates_balanced_entry(in_memory_db):
    svc, journal = _service(in_memory_db)
    svc.create(_asset())
    entry = svc.post_monthly_depreciation(2026, 6)
    assert entry is not None and entry.is_balanced
    dr = next(l for l in entry.lines if l.account_code == "642")
    cr = next(l for l in entry.lines if l.account_code == "214")
    assert dr.debit == Decimal("10000000")
    assert cr.credit == Decimal("10000000")


def test_post_is_idempotent(in_memory_db):
    svc, journal = _service(in_memory_db)
    svc.create(_asset())
    svc.post_monthly_depreciation(2026, 6)
    svc.post_monthly_depreciation(2026, 6)  # re-post must not duplicate
    matching = [e for e in journal.list_all() if e.ref == "KH-202606"]
    assert len(matching) == 1


def test_no_depreciation_returns_none(in_memory_db):
    svc, _ = _service(in_memory_db)
    svc.create(_asset(start=date(2026, 1, 1), life=3))  # hết KH sau tháng 3
    assert svc.post_monthly_depreciation(2026, 8) is None


def test_invalid_asset_rejected(in_memory_db):
    from domain.services.fixed_asset_service import FixedAssetValidationError

    svc, _ = _service(in_memory_db)
    with pytest.raises(FixedAssetValidationError):
        svc.create(_asset(cost="0"))
