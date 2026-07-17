"""Xóa toàn bộ dữ liệu nghiệp vụ để bàn giao cho kế toán nhập số liệu thật.

    python reset_data.py            # xóa sạch (có xác nhận)
    python reset_data.py --yes      # xóa sạch, không hỏi

Giữ lại hệ thống tài khoản (TT133/TT200) và cấu hình thông tư đang chọn; chỉ
xóa các chứng từ, hóa đơn, tồn kho, bảng kê giá thành, đối tác, mặt hàng… mà
dữ liệu mẫu hoặc người dùng đã nhập.
"""
from __future__ import annotations

import sys

from data.seed import reset_data


def main() -> int:
    # Windows consoles default to cp1252; force UTF-8 so Vietnamese prints.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    if "--yes" not in sys.argv:
        print("Se xoa toan bo chung tu/du lieu nghiep vu (giu lai he thong tai")
        print("khoan va thong tu). Thao tac khong the hoan tac.")
        answer = input("Go 'xoa' de xac nhan: ").strip().lower()
        if answer != "xoa":
            print("[--] Da huy - khong xoa gi.")
            return 1

    reset_data()
    print("[OK] Da xoa sach du lieu. Khoi dong ung dung: python main.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
