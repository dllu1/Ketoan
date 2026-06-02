"""JournalService tests — balanced double-entry rules, no Qt required."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.models.journal import EntryStatus, JournalEntry, JournalLine


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
    from domain.services.journal_service import JournalService

    return JournalService(JournalRepository(conn))


def _balanced(ref="PKT001", status=EntryStatus.POSTED):
    return JournalEntry(
        ref=ref,
        entry_date=date(2026, 6, 1),
        description="Thu tiền bán hàng",
        status=status,
        lines=[
            JournalLine(account_code="111", debit=Decimal("10000000")),
            JournalLine(account_code="511", credit=Decimal("10000000")),
        ],
    )


def test_create_persists_entry_and_lines(in_memory_db):
    service = _service(in_memory_db)
    saved = service.create(_balanced())
    assert saved.id is not None
    reloaded = service.list_all()[0]
    assert len(reloaded.lines) == 2
    assert reloaded.is_balanced


def test_balanced_posted_succeeds(in_memory_db):
    service = _service(in_memory_db)
    assert service.create(_balanced()).status is EntryStatus.POSTED


def test_unbalanced_posted_rejected(in_memory_db):
    from domain.services.journal_service import JournalValidationError

    service = _service(in_memory_db)
    entry = _balanced()
    entry.lines[1].credit = Decimal("9000000")
    with pytest.raises(JournalValidationError):
        service.create(entry)


def test_unbalanced_draft_allowed(in_memory_db):
    service = _service(in_memory_db)
    entry = _balanced(status=EntryStatus.DRAFT)
    entry.lines[1].credit = Decimal("9000000")
    assert service.create(entry).id is not None


def test_duplicate_ref_rejected(in_memory_db):
    from domain.services.journal_service import JournalValidationError

    service = _service(in_memory_db)
    service.create(_balanced(ref="PKT100"))
    with pytest.raises(JournalValidationError):
        service.create(_balanced(ref="PKT100"))


def test_line_with_both_debit_and_credit_rejected(in_memory_db):
    from domain.services.journal_service import JournalValidationError

    service = _service(in_memory_db)
    entry = _balanced()
    entry.lines[0].credit = Decimal("5000000")
    with pytest.raises(JournalValidationError):
        service.create(entry)


def test_delete_draft_but_not_posted(in_memory_db):
    from domain.services.journal_service import JournalValidationError

    service = _service(in_memory_db)
    draft = service.create(_balanced(ref="PKT-D", status=EntryStatus.DRAFT))
    posted = service.create(_balanced(ref="PKT-P"))

    service.delete(draft.id)
    assert all(e.id != draft.id for e in service.list_all())

    with pytest.raises(JournalValidationError):
        service.delete(posted.id)
