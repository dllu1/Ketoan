"""Mọi màn hình nạp dữ liệu đều phải tự làm mới được qua on_activated().

Chrome gọi ``screen.on_activated()`` mỗi lần mở màn hình và mỗi lần đổi kỳ kế
toán. Màn hình nào thiếu hook này sẽ đứng nguyên dữ liệu từ lúc khởi động —
đúng triệu chứng "bấm mà không đổi gì" người dùng gặp ở Tài sản cố định.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.period import Period, set_active_period  # noqa: E402

# Tên màn hình → (module, lớp); import lười để fixture DB tạm chạy trước.
_SCREENS = {
    "assets": ("ui.screens.assets_screen", "AssetsScreen"),
    "cash": ("ui.screens.cash_screen", "CashScreen"),
    "directory": ("ui.screens.directory_screen", "DirectoryScreen"),
    "reports": ("ui.screens.reports_screen", "ReportsScreen"),
    "tax": ("ui.screens.tax_screen", "TaxScreen"),
}


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


@pytest.mark.parametrize("name", sorted(_SCREENS))
def test_screen_refreshes_on_every_period(app, temp_db, name):
    from importlib import import_module

    module, class_name = _SCREENS[name]
    set_active_period(Period(year=2026, month=6))
    screen = getattr(import_module(module), class_name)()

    hook = getattr(screen, "on_activated", None)
    assert callable(hook), f"{class_name} thiếu on_activated() nên không tự làm mới"

    # Tháng, cả năm, rồi năm khác — kỳ "cả năm" (month=None) hay làm vỡ code
    # trót giả định lúc nào cũng có tháng.
    for period in (Period(2026, 6), Period(2025, None), Period(2026, 12)):
        set_active_period(period)
        hook()
