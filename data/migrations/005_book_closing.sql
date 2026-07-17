-- Phase 4: year-end book closing (chốt sổ cuối năm).
-- One row per fiscal year that has been closed; once present, every document
-- dated in that year is locked against create / edit / delete. `auto` flags a
-- closing performed automatically (48h after year-end with no manual closing).

CREATE TABLE IF NOT EXISTS book_closing (
    fiscal_year   INTEGER PRIMARY KEY,
    closed_at     TIMESTAMP NOT NULL,
    auto          INTEGER NOT NULL DEFAULT 0
);
