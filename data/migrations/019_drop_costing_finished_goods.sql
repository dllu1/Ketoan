-- Dọn các bút toán nhập kho thành phẩm do bảng giá thành tự đẩy (nguồn GT-TP).
--
-- Bối cảnh: trước đây CẢ HAI nơi cùng đẩy nhập kho 155 cho cùng một lô hàng —
-- Bảng kê TP đẩy nguồn 'BK-TP:<kỳ>', bảng giá thành đẩy thêm 'GT-TP:<kỳ>'. Số
-- lượng vì thế bị cộng đôi (vd 1.260 hiện thành 2.520) và Nhập·ĐG bị chia đôi
-- theo, trong khi Nhập·TT vẫn đúng vì chỉ một nguồn mang giá thành.
--
-- Bảng giá thành nay KHÔNG đẩy nhập kho nữa: số lượng do Bảng kê TP (155) làm
-- chủ, bảng giá thành chỉ cấp đơn giá. Migration này gỡ phần GT-TP tồn đọng.
--
-- Nguyên tắc: KHÔNG được làm mất tồn kho. Nên chia hai trường hợp thay vì xóa
-- sạch — với mã chỉ có GT-TP mà chưa hề có dòng trong bảng kê, xóa thẳng sẽ bốc
-- hơi lượng thành phẩm đang tồn.

-- 1) Mã chưa có dòng nào trong bảng kê TP: nhận nuôi thay vì xóa. Đổi nguồn
--    thành 'BK-TP:<kỳ>' để chính bảng kê làm chủ (lần lưu sau, bảng kê sẽ tự
--    thay thế trọn bộ movement của nguồn này). Ngày và giá trị giữ nguyên.
UPDATE inventory_movement
   SET source_ref = 'BK-TP:' || substr(source_ref, 7)
 WHERE source_ref LIKE 'GT-TP:%'
   AND NOT EXISTS (
       SELECT 1 FROM product_sheet_line p
        WHERE p.period_key = substr(inventory_movement.source_ref, 7)
          AND TRIM(p.code) = TRIM(inventory_movement.item_code)
   );

-- 2) Dựng dòng bảng kê tương ứng cho phần vừa nhận nuôi, để lượng nhập đó hiện
--    ra ở tab "Bảng kê TP (155)" và kéo được sang bảng Giá thành SP.
--    ĐG nhập = tổng tiền / tổng lượng (gộp phòng khi một mã có nhiều dòng).
INSERT INTO product_sheet_line (
    period_key, line_no, code, name, unit,
    opening_price, opening_qty, opening_value,
    in_price, in_qty, in_value,
    out_price, out_qty, out_value
)
SELECT substr(m.source_ref, 7),
       0,
       m.item_code,
       MAX(m.item_name),
       MAX(m.unit),
       0, 0, 0,
       CASE WHEN SUM(m.quantity) > 0
            THEN SUM(m.quantity * m.unit_cost) / SUM(m.quantity)
            ELSE 0 END,
       SUM(m.quantity),
       SUM(m.quantity * m.unit_cost),
       0, 0, 0
  FROM inventory_movement m
 WHERE m.source_ref LIKE 'BK-TP:%'
   AND m.kind = 'IN'
   AND TRIM(m.item_code) <> ''
   AND NOT EXISTS (
       SELECT 1 FROM product_sheet_line p
        WHERE p.period_key = substr(m.source_ref, 7)
          AND TRIM(p.code) = TRIM(m.item_code)
   )
 GROUP BY substr(m.source_ref, 7), m.item_code;

-- 3) Phần GT-TP còn lại đều là bản trùng của dòng bảng kê đã có → xóa. Đây chính
--    là phần gây nhân đôi số lượng.
DELETE FROM inventory_movement WHERE source_ref LIKE 'GT-TP:%';
