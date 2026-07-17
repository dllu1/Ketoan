-- Theo dõi công nợ chi tiết: gắn đối tượng (khách hàng / nhà cung cấp) vào
-- từng dòng bút toán — chủ yếu cho các tài khoản 131 / 331 trên phiếu thu/chi.

ALTER TABLE journal_line ADD COLUMN partner_code TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_journal_line_partner ON journal_line(partner_code);
