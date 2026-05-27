"""PartnerService tests — pure domain logic, no Qt required."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from domain.models.partner import Partner, PartnerType


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


def test_create_partner_assigns_id(in_memory_db):
    from data.repositories.partner_repo import PartnerRepository
    from domain.services.partner_service import PartnerService

    service = PartnerService(PartnerRepository(in_memory_db))
    saved = service.create(
        Partner(code="KH001", name="Công ty TNHH ABC", type=PartnerType.CUSTOMER)
    )
    assert saved.id is not None
    assert saved.code == "KH001"


def test_duplicate_code_rejected(in_memory_db):
    from data.repositories.partner_repo import PartnerRepository
    from domain.services.partner_service import PartnerService, PartnerValidationError

    service = PartnerService(PartnerRepository(in_memory_db))
    service.create(Partner(code="KH001", name="A"))
    with pytest.raises(PartnerValidationError):
        service.create(Partner(code="KH001", name="B"))


def test_invalid_tax_code_rejected(in_memory_db):
    from data.repositories.partner_repo import PartnerRepository
    from domain.services.partner_service import PartnerService, PartnerValidationError

    service = PartnerService(PartnerRepository(in_memory_db))
    with pytest.raises(PartnerValidationError):
        service.create(Partner(code="KH002", name="X", tax_code="abc"))


def test_valid_tax_codes_accepted(in_memory_db):
    from data.repositories.partner_repo import PartnerRepository
    from domain.services.partner_service import PartnerService

    service = PartnerService(PartnerRepository(in_memory_db))
    service.create(Partner(code="KH010", name="Ten-digit", tax_code="0123456789"))
    service.create(Partner(code="KH011", name="Branch", tax_code="0123456789-001"))
