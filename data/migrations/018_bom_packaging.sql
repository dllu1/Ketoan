-- Định mức theo quy cách đóng gói: với NVL bao gói (vd thùng carton) người dùng
-- chỉ biết "1 thùng chứa được N cây", khó tự tính định mức 1/N. pieces_per_pack
-- lưu N (số thành phẩm mà 1 đơn vị NVL bao được); khi > 0, định mức trên 1 thành
-- phẩm (quantity_per) được suy ra = 1/N. Bằng 0 nghĩa là nhập định mức trực tiếp.

ALTER TABLE bom_line ADD COLUMN pieces_per_pack NUMERIC NOT NULL DEFAULT 0;
