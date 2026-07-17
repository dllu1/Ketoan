-- Bảng kê Nhập–Xuất–Tồn thành phẩm (kho 155).
--
-- Same row shape as material_sheet_line, but the derivation rules differ (see
-- the handwritten form notes): Nhập·TT comes from the period's costing sheet
-- (giá thành), Xuất·ĐG is the weighted average (TT đầu + TT nhập) / (SL đầu +
-- SL nhập), and the opening balance carries forward from the previous period's
-- closing. Derived columns are still stored so reports can read the table flat.

CREATE TABLE IF NOT EXISTS product_sheet_line (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period_key      TEXT NOT NULL,
    line_no         INTEGER NOT NULL DEFAULT 0,
    code            TEXT NOT NULL DEFAULT '',
    name            TEXT NOT NULL DEFAULT '',
    unit            TEXT NOT NULL DEFAULT '',
    opening_price   NUMERIC NOT NULL DEFAULT 0,
    opening_qty     NUMERIC NOT NULL DEFAULT 0,
    opening_value   NUMERIC NOT NULL DEFAULT 0,
    in_price        NUMERIC NOT NULL DEFAULT 0,
    in_qty          NUMERIC NOT NULL DEFAULT 0,
    in_value        NUMERIC NOT NULL DEFAULT 0,
    out_price       NUMERIC NOT NULL DEFAULT 0,
    out_qty         NUMERIC NOT NULL DEFAULT 0,
    out_value       NUMERIC NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_product_sheet_period
    ON product_sheet_line(period_key);
