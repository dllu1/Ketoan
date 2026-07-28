"""AssetsScreen tự làm mới: on_activated, đổi kỳ, và chọn dòng không gọi DB.

Chạy headless (QT_QPA_PLATFORM=offscreen) trên một SQLite tạm.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.period import Period, set_active_period  # noqa: E402
from domain.models.fixed_asset import FixedAsset  # noqa: E402
from domain.money import format_money  # noqa: E402

_COL_ACCUMULATED = 7


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.config.DB_PATH", db_file)
    monkeypatch.setattr("data.database.DB_PATH", db_file)

    import data.database as db_mod
    db_mod._conn = None
    db_mod.init_database()
    yield db_mod.get_connection()
    db_mod.close_connection()


def _asset(code="TS001"):
    return FixedAsset(
        code=code, name="Máy CNC", asset_account="211", expense_account="15403",
        cost=Decimal("120000000"), useful_life_months=12,
        start_date=date(2026, 1, 1),
    )


def _screen(temp_db):
    from data.repositories.fixed_asset_repo import FixedAssetRepository
    from domain.services.fixed_asset_service import FixedAssetService
    from ui.screens.assets_screen import AssetsScreen

    set_active_period(Period(year=2026, month=6))
    return AssetsScreen(), FixedAssetService(FixedAssetRepository(temp_db))


def test_on_activated_picks_up_assets_added_later(app, temp_db):
    """Màn hình dựng sẵn từ lúc khởi động phải thấy TSCĐ mới khi quay lại tab."""
    screen, service = _screen(temp_db)
    assert screen._table.rowCount() == 0

    service.create(_asset())
    screen.on_activated()

    assert screen._table.rowCount() == 1
    assert screen._table.item(0, 0).text() == "TS001"


def test_on_activated_follows_the_active_period(app, temp_db):
    """Đổi kỳ ở thanh trên → cột lũy kế tính đến đúng kỳ đó."""
    screen, service = _screen(temp_db)
    service.create(_asset())

    set_active_period(Period(year=2026, month=3))
    screen.on_activated()
    assert screen._table.item(0, _COL_ACCUMULATED).text() == format_money(
        Decimal("30000000")
    )

    set_active_period(Period(year=2026, month=9))
    screen.on_activated()
    assert screen._table.item(0, _COL_ACCUMULATED).text() == format_money(
        Decimal("90000000")
    )


def test_changing_month_reloads_the_table(app, temp_db):
    """Bấm combo Tháng phải thấy bảng đổi số, không đứng im."""
    screen, service = _screen(temp_db)
    service.create(_asset())
    screen.on_activated()

    screen._month.setCurrentIndex(0)  # tháng 01
    assert screen._table.item(0, _COL_ACCUMULATED).text() == format_money(
        Decimal("10000000")
    )


def test_selecting_a_row_does_not_query_the_database(app, temp_db, monkeypatch):
    """Di chuyển con trỏ chỉ đọc cache — trước đây mỗi lần đổi ô là một lần
    list_all() nên danh mục lớn là giật/treo."""
    screen, service = _screen(temp_db)
    service.create(_asset("TS001"))
    service.create(_asset("TS002"))
    screen.on_activated()

    calls: list[int] = []
    original = screen._service.list_all
    monkeypatch.setattr(
        screen._service, "list_all",
        lambda: (calls.append(1), original())[1],
    )
    screen._table.setCurrentCell(1, 0)
    screen._table.setCurrentCell(0, 0)

    assert calls == []
    assert screen._schedule.rowCount() == 12  # lưới khấu hao vẫn dựng đúng
