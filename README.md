# Hưng Phát Accounting Suite

<samp>**Tiếng Việt** · [English](README.en.md) · [中文](README.zh.md) · [Français](README.fr.md)</samp>

Phần mềm kế toán desktop cho doanh nghiệp Việt Nam, xây dựng bằng **Python + PySide6**.
Hỗ trợ chế độ kế toán theo **Thông tư 200** và **Thông tư 133** (chuyển đổi được),
lưu trữ cục bộ bằng **SQLite** — không cần máy chủ, chạy hoàn toàn trên máy người dùng.

> Tên hiển thị trong ứng dụng: *Hung Phat Accounting* — đơn vị: *Hung Phat M&E*.

---

## Tính năng chính

| Phân hệ | Mô tả |
|---|---|
| **Tổng quan** | Bảng điều khiển: doanh thu/chi phí, công nợ, biểu đồ xu hướng, chỉ số nhanh. |
| **Sổ nhật ký chung** | Nhập bút toán tổng hợp, gắn đối tác theo từng dòng (TK 131/331). |
| **Danh mục** | Hệ thống tài khoản, khách hàng/NCC, mặt hàng, kho. |
| **Bán hàng / Mua hàng** | Chứng từ hóa đơn đầu ra/đầu vào, tự sinh bút toán và ghi nhận kho. |
| **Quỹ** | Phiếu thu/chi tiền mặt & ngân hàng, chọn đối tác cho công nợ. |
| **Kho hàng** | Bảng Nhập–Xuất–Tồn NVL và tính **giá thành** (phân bổ theo tỉ lệ NVL). |
| **Tài sản cố định** | Quản lý TSCĐ và khấu hao. |
| **Thuế** | Tờ khai GTGT / TNDN, tự điền sẵn thông tin công ty. |
| **Báo cáo** | Sổ cái, sổ chi tiết, bảng cân đối, kết quả kinh doanh; xuất Excel/PDF. |
| **Hóa đơn điện tử (HĐĐT)** | Tự lấy hóa đơn từ email (IMAP), phân tích XML → chứng từ nháp. |
| **Chốt sổ cuối năm** | Khóa dữ liệu năm tài chính; tự chốt sau 48 giờ nếu không thao tác. |

### Lấy hóa đơn điện tử từ email

- Kết nối hộp thư qua **IMAP** với hai cách xác thực: **OAuth2 (XOAUTH2)** cho Gmail
  hoặc **App Password / mật khẩu IMAP** (Yahoo, IMAP tùy chỉnh).
- Phân tích **XML HĐĐT theo chuẩn TT78/NĐ123** (thẻ `TTChung`, `NDHDon`, `NBan`,
  `NMua`, `DSHHDVu`…), tương thích hầu hết nhà cung cấp (Viettel, VNPT, MISA, BKAV…).
- Đọc được cả **XML nén trong file `.zip`**; PDF đính kèm được lưu lại để tra cứu.
- **Tự phân loại mua/bán theo MST công ty**: MST người bán trùng công ty → hóa đơn
  **bán ra** (đối tác = người mua); còn lại → **mua vào**.
  - Hóa đơn **mua vào** thường nằm ở `INBOX` (cổng HĐĐT gửi về).
  - Hóa đơn **bán ra** do bạn tự soạn email gửi khách nằm ở `[Gmail]/Sent Mail`.
- Nút **"Quét lại từ đầu"** đặt lại mốc UID để duyệt lại toàn bộ thư (chống trùng
  bằng số chứng từ).

Hướng dẫn chi tiết có sẵn trong ứng dụng: **Hướng dẫn sử dụng → "Tự động lấy hóa đơn
điện tử (HĐĐT) từ email"**.

---

## Yêu cầu hệ thống

- **Python ≥ 3.11**
- Windows (đã kiểm thử trên Windows 11); có thể chạy trên nền tảng khác mà PySide6 hỗ trợ.

## Cài đặt & chạy

```bash
# 1) Tạo môi trường ảo
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

# 2) Cài đặt phụ thuộc (kèm nhóm xuất báo cáo)
pip install -e ".[reports]"

# 3) Chạy ứng dụng
python main.py
```

Muốn cài kèm công cụ kiểm thử: `pip install -e ".[dev,reports]"`.

### Dữ liệu người dùng

Cơ sở dữ liệu và tệp đính kèm được lưu ngoài mã nguồn, tại:

```
%APPDATA%\HungPhatAccounting\
├── ketoan.db          # toàn bộ dữ liệu kế toán (SQLite)
└── einvoices\         # PDF hóa đơn tải từ email
```

Lần chạy đầu, ứng dụng tự tạo cơ sở dữ liệu và nạp sẵn hệ thống tài khoản.

### Dữ liệu mẫu & làm sạch

Trong **Cấu hình → Dữ liệu mẫu (Demo)**:
- **Nạp dữ liệu mẫu** — tạo một năm số liệu đầy đủ để dùng thử.
- **Xóa toàn bộ dữ liệu** — bắt đầu nhập số liệu thật (luôn giữ hệ thống tài khoản
  và thông tư đang chọn).

---

## Cấu trúc dự án

```
Ketoan/
├── main.py                  # Điểm khởi động (QApplication + ChromeWindow)
├── app/                     # Cấu hình, theme, poller email, phím tắt
├── domain/                  # Nghiệp vụ thuần Python (không phụ thuộc UI)
│   ├── models/              #   Dataclass: Invoice, Journal, Partner, Item…
│   └── services/            #   Logic: bán/mua, kho, giá thành, thuế, HĐĐT…
├── data/                    # Tầng dữ liệu
│   ├── database.py          #   Kết nối SQLite dùng chung
│   ├── migrations/          #   *.sql tạo/nâng cấp schema theo thứ tự
│   ├── repositories/        #   Truy vấn từng bảng
│   └── email/               #   IMAP client + OAuth (lấy HĐĐT)
├── ui/                      # Giao diện PySide6
│   ├── chrome/              #   Khung cửa sổ, sidebar, thanh trạng thái
│   ├── screens/             #   Từng màn hình phân hệ
│   ├── modals/ primitives/  #   Hộp thoại & widget tái dùng
│   └── resources/           #   QSS, font, icon
├── reports/exporters/       # Xuất Excel (openpyxl) / PDF (reportlab)
└── tests/                   # pytest (domain, data, reports, ui)
```

### Kiến trúc

Phân lớp rõ ràng: **UI → domain services → repositories → SQLite**. Tầng `domain`
không import PySide6 nên kiểm thử được độc lập, không cần GUI. Mọi thao tác SQLite
đi qua một kết nối dùng chung trên main thread; tác vụ mạng (IMAP) chạy trong
`QThread` rồi trả kết quả về main thread để ghi DB an toàn.

---

## Cơ sở dữ liệu

Schema được quản lý bằng các tệp trong `data/migrations/` (đặt tên `NNN_ten.sql`),
chạy tuần tự khi khởi động. Thêm thay đổi schema bằng cách tạo tệp migration mới có
số thứ tự kế tiếp — không sửa tệp cũ đã phát hành.

## Kiểm thử

```bash
python -m pytest --basetemp=.pytest_tmp
```

> ⚠️ Trên Windows cần cờ `--basetemp=.pytest_tmp`, nếu không các test dùng thư mục
> tạm sẽ gặp lỗi quyền truy cập.

Test tập trung ở tầng `domain`/`data` (không cần GUI). Ví dụ liên quan HĐĐT:
`tests/domain/test_einvoice_parser.py`, `tests/domain/test_invoice_import_service.py`,
`tests/domain/test_email_config_service.py`, `tests/data/test_imap_client.py`.

---

## Ghi chú phát triển

- **Phụ thuộc runtime**: `PySide6`, `google-auth`, `google-auth-oauthlib`
  (xem `pyproject.toml`). Nhóm tùy chọn: `reports` (openpyxl, reportlab),
  `dev` (pytest, pytest-qt).
- **Mô hình ghi sổ**: khóa theo **chốt sổ cuối năm** thay cho khóa từng chứng từ.
- **Bảo mật cục bộ**: mật khẩu/OAuth token chỉ được *obfuscate* base64 trong bảng
  `settings` — đây là máy cá nhân, không phải lớp bảo mật thật (keyring nằm ngoài
  phạm vi hiện tại).
