-- Chi phí trả trước (TK 242 / 1421 / 1422) phân bổ dần theo tháng.
-- Sổ tay "Nhập liệu" mục I.3.d: hóa đơn đầu vào loại chi phí dùng cho nhiều kỳ
-- thì không tính hết một lần mà treo vào TK chi phí trả trước rồi phân bổ ra
-- từng tháng (bảng STT · Tên · Số tiền · Số tháng · T01…T12 · Số còn lại).
--   total_amount    tổng tiền phải phân bổ
--   months          số tháng phân bổ
--   start_year/…    tháng bắt đầu phân bổ
--   expense_account TK chi phí nhận phân bổ hằng tháng (642, 641, 627…)
--   asset_account   TK treo chi phí trả trước (242 mặc định, hoặc 1421/1422)

CREATE TABLE IF NOT EXISTS prepaid_expense (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL DEFAULT '',
    total_amount    TEXT NOT NULL DEFAULT '0',
    months          INTEGER NOT NULL DEFAULT 1,
    start_year      INTEGER NOT NULL,
    start_month     INTEGER NOT NULL,
    expense_account TEXT NOT NULL DEFAULT '642',
    asset_account   TEXT NOT NULL DEFAULT '242',
    note            TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_prepaid_start
    ON prepaid_expense (start_year, start_month);
