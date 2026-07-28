-- ĐVT ghi trên chứng từ (vd mua hàng nhập "kg") phải theo hàng vào kho, thay vì
-- bị ĐVT mặc định của danh mục ("Cái") đè lên khi hiện ở Nhập–Xuất–Tồn.
-- Lưu ĐVT ngay trên từng lượt phát sinh, giống item_name đã denormalize sẵn.

ALTER TABLE inventory_movement ADD COLUMN unit TEXT NOT NULL DEFAULT '';
