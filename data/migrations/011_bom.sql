-- Phase 4: định mức nguyên vật liệu (bill of materials) for finished products.
--
-- One row per (product_code, material_code): how much of an NVL (kho 152) goes
-- into one unit of a finished product (kho 155). Drives the direct-material
-- column of the costing worksheet (Bảng tính giá thành).

CREATE TABLE IF NOT EXISTS bom_line (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code    TEXT NOT NULL,
    material_code   TEXT NOT NULL,
    quantity_per    NUMERIC NOT NULL DEFAULT 0,
    note            TEXT NOT NULL DEFAULT '',
    UNIQUE(product_code, material_code)
);

CREATE INDEX IF NOT EXISTS idx_bom_product ON bom_line(product_code);
