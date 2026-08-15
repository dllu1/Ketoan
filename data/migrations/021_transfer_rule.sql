-- Quy tắc kết chuyển do người dùng tự định nghĩa (thay cho danh sách cứng).
--
-- Trước đây ResultService gắn chết 511/512/515/711 là doanh thu và
-- 632/635/641/642/811/812/821 là chi phí, luôn kết chuyển sang 911. Nay mỗi
-- dòng ở bảng này là một quy tắc: TK nguồn → TK đích, theo chiều người dùng
-- chọn, gom vào một số chứng từ (group_ref).
--
--   direction = 'DEBIT_SOURCE'   Nợ TK nguồn / Có TK đích  (vd: 515 → Có 911)
--   direction = 'CREDIT_SOURCE'  Có TK nguồn / Nợ TK đích  (vd: 642 → Nợ 911)
--
-- include_children = 1 thì TK con cũng thuộc quy tắc (5111 theo 511); khi một
-- mã khớp nhiều quy tắc thì quy tắc có mã nguồn DÀI NHẤT thắng, nên khai thêm
-- 5111 riêng vẫn tách được khỏi 511.

CREATE TABLE IF NOT EXISTS transfer_rule (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    group_ref        TEXT    NOT NULL DEFAULT 'KC-CP',
    label            TEXT    NOT NULL DEFAULT '',
    source_account   TEXT    NOT NULL,
    target_account   TEXT    NOT NULL DEFAULT '911',
    direction        TEXT    NOT NULL DEFAULT 'DEBIT_SOURCE',
    include_children INTEGER NOT NULL DEFAULT 1,
    sort_order       INTEGER NOT NULL DEFAULT 0,
    active           INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_transfer_rule_order
    ON transfer_rule (sort_order, source_account);
