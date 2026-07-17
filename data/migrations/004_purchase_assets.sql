-- Phase 3 (cont.): purchases reuse the invoice table via a kind discriminator;
-- fixed assets get their own table.

ALTER TABLE invoice ADD COLUMN kind TEXT NOT NULL DEFAULT 'SALE';

CREATE INDEX IF NOT EXISTS idx_invoice_kind ON invoice(kind);

CREATE TABLE IF NOT EXISTS fixed_asset (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT NOT NULL UNIQUE,
    name                TEXT NOT NULL,
    asset_account       TEXT NOT NULL DEFAULT '211',   -- 211 hữu hình / 213 vô hình
    expense_account     TEXT NOT NULL DEFAULT '642',   -- TK chi phí khấu hao (627/641/642)
    cost                NUMERIC NOT NULL DEFAULT 0,     -- nguyên giá
    salvage_value       NUMERIC NOT NULL DEFAULT 0,     -- giá trị thu hồi ước tính
    useful_life_months  INTEGER NOT NULL DEFAULT 12,
    start_date          TEXT NOT NULL,
    notes               TEXT NOT NULL DEFAULT '',
    active              INTEGER NOT NULL DEFAULT 1,
    created_at          TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fixed_asset_code ON fixed_asset(code);
