-- Tài khoản tổng hợp: mỗi tài khoản có thể trỏ tới một "tài khoản cha" (tổng
-- hợp). Số dư của tài khoản cha = số dư riêng của nó + tổng số dư các con.
-- parent_code trỏ tới account.code; rỗng nghĩa là tài khoản không có cha.

ALTER TABLE account ADD COLUMN parent_code TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_account_parent ON account(parent_code);
