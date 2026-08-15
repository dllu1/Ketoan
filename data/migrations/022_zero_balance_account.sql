-- Tài khoản phải về 0 (không còn số dư) vào cuối kỳ — do người dùng tự khai.
--
-- Các TK kết quả kinh doanh (511, 632, 641, 642, 911…) sau khi kết chuyển phải
-- hết số dư; còn dư là dấu hiệu thiếu quy tắc kết chuyển, sai chiều Nợ/Có, hay
-- có bút toán ghi sau khi đã kết chuyển. Danh sách này để chương trình kiểm tra
-- và cảnh báo, KHÔNG tự sửa sổ.
--
-- include_children = 1 thì TK con cũng bị kiểm tra (5111 theo 511); khi một mã
-- khớp nhiều dòng thì dòng có mã DÀI NHẤT thắng, nên khai riêng một TK con với
-- dung sai khác vẫn được.
--
-- tolerance là số tiền lệch còn chấp nhận được (lưu dạng text để giữ Decimal),
-- dành cho chênh lệch làm tròn khi phân bổ giá thành. Mặc định 0 = phải sạch.

CREATE TABLE IF NOT EXISTS zero_balance_account (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    account_code     TEXT    NOT NULL,
    include_children INTEGER NOT NULL DEFAULT 1,
    tolerance        TEXT    NOT NULL DEFAULT '0',
    note             TEXT    NOT NULL DEFAULT '',
    sort_order       INTEGER NOT NULL DEFAULT 0,
    active           INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_zero_balance_order
    ON zero_balance_account (sort_order, account_code);
