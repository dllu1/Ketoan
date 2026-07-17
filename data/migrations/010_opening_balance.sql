-- Phase 4: opening balances (số dư đầu kỳ) per fiscal year.
--
-- One row per (fiscal_year, account_code, item_code). An empty item_code marks
-- an account-level opening (Nợ/Có đầu kỳ); a set item_code marks a stock detail
-- line (152/155/156) carrying opening quantity + value. Reports add these as a
-- baseline so a period whose prior year has no postings still shows an opening.

CREATE TABLE IF NOT EXISTS opening_balance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fiscal_year     INTEGER NOT NULL,
    account_code    TEXT NOT NULL,
    item_code       TEXT NOT NULL DEFAULT '',
    opening_debit   NUMERIC NOT NULL DEFAULT 0,
    opening_credit  NUMERIC NOT NULL DEFAULT 0,
    opening_qty     NUMERIC NOT NULL DEFAULT 0,
    opening_value   NUMERIC NOT NULL DEFAULT 0,
    UNIQUE(fiscal_year, account_code, item_code)
);

CREATE INDEX IF NOT EXISTS idx_opening_year ON opening_balance(fiscal_year);
