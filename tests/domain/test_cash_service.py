"""CashService tests — phiếu thu/chi as journal vouchers + derived balances."""
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
    from data.repositories.journal_repo import JournalRepository
    from domain.services.cash_service import CashService
    from domain.services.journal_service import JournalService

    return CashService(JournalService(JournalRepository(conn)), AccountRepository(conn))


def test_receipt_increases_cash_balance(in_memory_db):
    from domain.models.cash import CashKind

    svc = _service(in_memory_db)
    entry = svc.create_voucher(
        kind=CashKind.RECEIPT, ref="PT001", cash_account="111",
        counter_account="511", amount=Decimal("10000000"),
        entry_date=date(2026, 6, 1), description="Thu tiền bán hàng",
    )
    assert entry.is_balanced
    assert svc.balance("111") == Decimal("10000000")


def test_payment_decreases_cash_balance(in_memory_db):
    from domain.models.cash import CashKind

    svc = _service(in_memory_db)
    svc.create_voucher(kind=CashKind.RECEIPT, ref="PT001", cash_account="111",
                       counter_account="511", amount=Decimal("10000000"))
    svc.create_voucher(kind=CashKind.PAYMENT, ref="PC001", cash_account="111",
                       counter_account="642", amount=Decimal("3000000"))
    assert svc.balance("111") == Decimal("7000000")


def test_movements_carry_running_balance(in_memory_db):
    from domain.models.cash import CashKind

    svc = _service(in_memory_db)
    svc.create_voucher(kind=CashKind.RECEIPT, ref="PT001", cash_account="111",
                       counter_account="511", amount=Decimal("5000000"),
                       entry_date=date(2026, 6, 1))
    svc.create_voucher(kind=CashKind.PAYMENT, ref="PC001", cash_account="111",
                       counter_account="331", amount=Decimal("2000000"),
                       entry_date=date(2026, 6, 2))
    movements = svc.list_movements("111")
    assert len(movements) == 2
    # newest first → latest running balance on top.
    assert movements[0].balance == Decimal("3000000")
    assert movements[0].outflow == Decimal("2000000")


def test_invalid_voucher_rejected(in_memory_db):
    from domain.models.cash import CashKind
    from domain.services.cash_service import CashValidationError

    svc = _service(in_memory_db)
    with pytest.raises(CashValidationError):
        svc.create_voucher(kind=CashKind.RECEIPT, ref="PT001", cash_account="111",
                           counter_account="511", amount=Decimal("0"))
    with pytest.raises(CashValidationError):
        svc.create_voucher(kind=CashKind.RECEIPT, ref="PT002", cash_account="999",
                           counter_account="511", amount=Decimal("1000"))
