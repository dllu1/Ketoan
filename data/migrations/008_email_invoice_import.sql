-- Phase 8: nhập hóa đơn điện tử (HĐĐT) từ email.
--
-- Chứng từ tạo từ email mang thêm:
--   * source          = nguồn tạo chứng từ ('' = nhập tay, 'EMAIL' = lấy từ hộp thư)
--   * attachment_path  = đường dẫn file PDF gốc lưu kèm (USER_DATA_DIR/einvoices/<ref>.pdf)
-- Giá trị rỗng giữ nguyên hành vi cũ cho mọi chứng từ đã có.

ALTER TABLE invoice ADD COLUMN source TEXT NOT NULL DEFAULT '';
ALTER TABLE invoice ADD COLUMN attachment_path TEXT NOT NULL DEFAULT '';
