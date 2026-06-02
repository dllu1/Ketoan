"""AccountService tests — circular switching is additive and safe."""
from __future__ import annotations

import pytest

from domain.models.account import Account


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
    from data.repositories.settings_repo import SettingsRepository
    from domain.services.account_service import AccountService

    return AccountService(AccountRepository(conn), SettingsRepository(conn))


def test_ensure_seeded_loads_tt133(in_memory_db):
    service = _service(in_memory_db)
    service.ensure_seeded()
    codes = {a.code for a in service.list_all()}
    assert "642" in codes          # Chi phí quản lý kinh doanh (TT133)
    assert "641" not in codes      # TT133 has no separate selling-expense account
    assert service.active_circular() == "TT133"


def test_switch_to_tt200_is_additive_and_reports_conflicts(in_memory_db):
    service = _service(in_memory_db)
    service.ensure_seeded()
    before = {a.code for a in service.list_all()}

    result = service.set_circular("TT200")

    after = {a.code: a for a in service.list_all()}
    # nothing deleted, only growth
    assert before.issubset(after.keys())
    assert "641" in after            # TT200-only account added
    assert result.added > 0
    assert service.active_circular() == "TT200"
    # 642 exists in both with a different name → reported, not overwritten
    assert any(code == "642" for code, _, _ in result.conflicts)
    assert after["642"].name == "Chi phí quản lý kinh doanh"  # original TT133 name kept


def test_switch_back_deletes_nothing(in_memory_db):
    service = _service(in_memory_db)
    service.ensure_seeded()
    service.set_circular("TT200")
    count_after_tt200 = len(service.list_all())

    service.set_circular("TT133")
    assert len(service.list_all()) == count_after_tt200  # additive-only, no deletions


def test_create_and_duplicate_validation(in_memory_db):
    from domain.services.account_service import AccountValidationError

    service = _service(in_memory_db)
    service.create(Account(code="99999", name="Tài khoản tùy chỉnh"))
    with pytest.raises(AccountValidationError):
        service.create(Account(code="99999", name="Trùng mã"))
