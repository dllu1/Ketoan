-- Phase 5: production-costing worksheets.
--   * material_sheet_line — "Bảng kê Nhập–Xuất–Tồn nguyên vật liệu chính"
--     (one editable row per material, keyed by accounting period). Tồn cuối kỳ
--     is derived (đầu kỳ + nhập − xuất); a sheet whose closing goes negative is
--     refused at save time, so no negative-closing row is ever persisted here.
--   * costing_sheet / costing_product — "Bảng tính giá thành sản phẩm". The
--     three non-material cost pools live on the sheet; each finished product
--     carries its quantity and direct-material (NVL/15401) amount. The labor /
--     overhead / other pools are split across products by NVL ratio at compute
--     time, so only the raw inputs are stored.

CREATE TABLE IF NOT EXISTS material_sheet_line (
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

CREATE INDEX IF NOT EXISTS idx_material_sheet_period
    ON material_sheet_line(period_key);

CREATE TABLE IF NOT EXISTS costing_sheet (
    period_key      TEXT PRIMARY KEY,
    labor_pool      NUMERIC NOT NULL DEFAULT 0,   -- 15402 · nhân công / tương ứng
    overhead_pool   NUMERIC NOT NULL DEFAULT 0,   -- 154032 · sản xuất chung
    other_pool      NUMERIC NOT NULL DEFAULT 0    -- 154033 · chi phí khác
);

CREATE TABLE IF NOT EXISTS costing_product (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    period_key      TEXT NOT NULL,
    line_no         INTEGER NOT NULL DEFAULT 0,
    code            TEXT NOT NULL DEFAULT '',
    name            TEXT NOT NULL DEFAULT '',
    quantity        NUMERIC NOT NULL DEFAULT 0,
    material_cost   NUMERIC NOT NULL DEFAULT 0    -- 15401 · NVL trực tiếp (định mức)
);

CREATE INDEX IF NOT EXISTS idx_costing_product_period
    ON costing_product(period_key);
