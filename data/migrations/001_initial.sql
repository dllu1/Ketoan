CREATE TABLE IF NOT EXISTS partner (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL CHECK(type IN ('CUSTOMER','SUPPLIER','BOTH')),
    tax_code        TEXT NOT NULL DEFAULT '',
    address         TEXT NOT NULL DEFAULT '',
    phone           TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    contact_person  TEXT NOT NULL DEFAULT '',
    bank_account    TEXT NOT NULL DEFAULT '',
    bank_name       TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_partner_name ON partner(name);
CREATE INDEX IF NOT EXISTS idx_partner_type ON partner(type);

CREATE TABLE IF NOT EXISTS item (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL CHECK(category IN ('152','153','155','156')),
    unit            TEXT NOT NULL DEFAULT 'Cái',
    unit_price      NUMERIC NOT NULL DEFAULT 0,
    vat_rate        NUMERIC NOT NULL DEFAULT 10,
    account_code    TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_item_name ON item(name);
CREATE INDEX IF NOT EXISTS idx_item_category ON item(category);
