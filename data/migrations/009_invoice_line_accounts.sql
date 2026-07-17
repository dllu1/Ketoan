-- Per-line định khoản Nợ/Có cho dòng hàng hóa đơn.
-- Mỗi mặt hàng trên một hóa đơn có thể được định khoản vào tài khoản Nợ/Có
-- khác nhau (độc lập với TK kho dùng cho nhập–xuất–tồn). Rỗng = kế thừa định
-- khoản đầu chứng từ rồi tới mặc định theo loại chứng từ / hình thức thanh toán.

ALTER TABLE invoice_line ADD COLUMN debit_account TEXT NOT NULL DEFAULT '';
ALTER TABLE invoice_line ADD COLUMN credit_account TEXT NOT NULL DEFAULT '';
