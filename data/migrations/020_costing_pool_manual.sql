-- Cờ "người dùng đã sửa tay" cho ba pool chi phí của bảng tính giá thành.
--
-- Trước đây mỗi lần mở lại tab Giá thành SP, ba ô Nhân công / SX chung / Chi phí
-- khác đều bị tính lại từ sổ cái và ghi đè số đã nhập, nên con số không bao giờ
-- đứng yên. Nay ô nào người dùng đã gõ vào thì được đánh dấu manual = 1 và giữ
-- nguyên; ô chưa động tới vẫn tự lấy từ sổ cái như cũ.

ALTER TABLE costing_sheet ADD COLUMN labor_manual    INTEGER NOT NULL DEFAULT 0;
ALTER TABLE costing_sheet ADD COLUMN overhead_manual INTEGER NOT NULL DEFAULT 0;
ALTER TABLE costing_sheet ADD COLUMN other_manual    INTEGER NOT NULL DEFAULT 0;
