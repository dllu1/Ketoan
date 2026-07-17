-- Phase 3: sales documents (hóa đơn bán hàng) + inventory movements (NXT).

CREATE TABLE IF NOT EXISTS invoice (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ref                 TEXT NOT NULL UNIQUE,
    invoice_no          TEXT NOT NULL DEFAULT '',
    serial              TEXT NOT NULL DEFAULT '',
    invoice_date        TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'POSTED' CHECK(status IN ('DRAFT','POSTED')),
    payment_method      TEXT NOT NULL DEFAULT 'CREDIT' CHECK(payment_method IN ('CASH','BANK','CREDIT')),
    partner_code        TEXT NOT NULL DEFAULT '',
    partner_name        TEXT NOT NULL DEFAULT '',
    partner_tax_code    TEXT NOT NULL DEFAULT '',
    partner_address     TEXT NOT NULL DEFAULT '',
    description         TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMP NOT NULL,
    updated_at          TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_invoice_date ON invoice(invoice_date);
CREATE INDEX IF NOT EXISTS idx_invoice_partner ON invoice(partner_code);

CREATE TABLE IF NOT EXISTS invoice_line (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id      INTEGER NOT NULL REFERENCES invoice(id) ON DELETE CASCADE,
    line_no         INTEGER NOT NULL DEFAULT 0,
    item_code       TEXT NOT NULL DEFAULT '',
    item_name       TEXT NOT NULL DEFAULT '',
    unit            TEXT NOT NULL DEFAULT '',
    quantity        NUMERIC NOT NULL DEFAULT 0,
    unit_price      NUMERIC NOT NULL DEFAULT 0,
    vat_rate        NUMERIC NOT NULL DEFAULT 10,
    account_code    TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_invoice_line_invoice ON invoice_line(invoice_id);

CREATE TABLE IF NOT EXISTS inventory_movement (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_code       TEXT NOT NULL,
    item_name       TEXT NOT NULL DEFAULT '',
    account_code    TEXT NOT NULL DEFAULT '',
    move_date       TEXT NOT NULL,
    kind            TEXT NOT NULL CHECK(kind IN ('OPENING','IN','OUT')),
    quantity        NUMERIC NOT NULL DEFAULT 0,
    unit_cost       NUMERIC NOT NULL DEFAULT 0,
    source_ref      TEXT NOT NULL DEFAULT '',
    note            TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_movement_item ON inventory_movement(item_code);
CREATE INDEX IF NOT EXISTS idx_movement_date ON inventory_movement(move_date);
CREATE INDEX IF NOT EXISTS idx_movement_source ON inventory_movement(source_ref);
