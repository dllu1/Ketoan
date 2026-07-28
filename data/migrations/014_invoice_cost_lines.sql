-- Tách dòng hóa đơn mua hàng thành hai loại.
--   'ITEM' — nguyên vật liệu / hàng hóa: có số lượng + đơn giá, chạy nhập kho.
--   'COST' — phí dịch vụ mua ngoài (giao hàng, điện, nước…): chỉ có thành tiền,
--            không vào kho, chỉ ghi Nợ TK chi phí / Có phải trả.
-- allocation_target = tài khoản sẽ nhận chi phí này khi phân bổ / kết chuyển
-- (vd '155' giá thành thành phẩm, '154', '632'…). Người dùng chọn trên chứng từ.

ALTER TABLE invoice_line ADD COLUMN line_type TEXT NOT NULL DEFAULT 'ITEM';
ALTER TABLE invoice_line ADD COLUMN allocation_target TEXT NOT NULL DEFAULT '';
