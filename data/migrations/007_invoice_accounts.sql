-- Phase 7: định khoản Nợ/Có trên chứng từ mua hàng / bán hàng.
--
-- Each document now carries an editable counter-account pair so the posting can
-- be re-routed without code changes:
--   * SALE     → debit_account = tiền/phải thu (Nợ), credit_account = doanh thu (Có)
--   * PURCHASE → debit_account = kho mặc định (Nợ),  credit_account = phải trả/tiền (Có)
-- An empty value falls back to the legacy default (payment_method / 511 / 156),
-- so existing rows keep their behaviour.

ALTER TABLE invoice ADD COLUMN debit_account TEXT NOT NULL DEFAULT '';
ALTER TABLE invoice ADD COLUMN credit_account TEXT NOT NULL DEFAULT '';
