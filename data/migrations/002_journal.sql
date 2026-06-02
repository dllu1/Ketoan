-- Phase 2: configurable circular (settings + chart of accounts) + general journal.

CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL DEFAULT '',
    circular        TEXT NOT NULL DEFAULT '',
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_account_code ON account(code);

CREATE TABLE IF NOT EXISTS journal_entry (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ref             TEXT NOT NULL UNIQUE,
    entry_date      TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'POSTED' CHECK(status IN ('DRAFT','POSTED')),
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_journal_entry_date ON journal_entry(entry_date);
CREATE INDEX IF NOT EXISTS idx_journal_entry_status ON journal_entry(status);

CREATE TABLE IF NOT EXISTS journal_line (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id        INTEGER NOT NULL REFERENCES journal_entry(id) ON DELETE CASCADE,
    line_no         INTEGER NOT NULL DEFAULT 0,
    account_code    TEXT NOT NULL,
    account_name    TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    debit           NUMERIC NOT NULL DEFAULT 0,
    credit          NUMERIC NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_journal_line_entry ON journal_line(entry_id);
