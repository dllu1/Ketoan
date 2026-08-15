# Đóng gói bản phát hành

Mọi thứ cần để tạo bản Windows gửi cho người dùng nằm trong thư mục này.

## Build

```powershell
.\packaging\build.ps1 -Clean
```

Script sẽ: cài PyInstaller nếu thiếu → build theo `ketoan.spec` → **chạy thử file
.exe 12 giây** (build nào chết ngay lúc khởi động sẽ bị chặn, không đóng gói) →
nén ZIP.

Kết quả trong `dist/`:

| File | Dùng để |
|---|---|
| `HungPhatAccounting/` | Thư mục chạy được (test tại chỗ) |
| `HungPhatAccounting-<version>-win64.zip` | **Bản upload / gửi người dùng** |
| `HungPhatAccounting-Setup-<version>.exe` | Bộ cài, chỉ khi dùng `-Installer` |

Thêm `-Installer` nếu muốn bộ cài `.exe` (cần [Inno Setup 6](https://jrsoftware.org/isdl.php)).

## Các file trong thư mục này

| File | Vai trò |
|---|---|
| `ketoan.spec` | Cấu hình PyInstaller: tài nguyên nhúng, module Qt loại bỏ |
| `build.ps1` | Script build + smoke test + nén |
| `installer.iss` | Script Inno Setup (bộ cài tùy chọn) |
| `version_info.txt` | Metadata hiện trong Properties của file .exe |
| `HungPhat.ico` | Icon ứng dụng |
| `make_icon.py` | Sinh lại `HungPhat.ico` (chỉ chạy khi đổi màu thương hiệu) |
| `HUONG-DAN.txt` | Hướng dẫn kèm trong ZIP cho người dùng cuối |

## Vì sao one-folder chứ không phải một file .exe duy nhất

PySide6 nặng ~150 MB. Bản one-file phải giải nén toàn bộ ra thư mục tạm **mỗi
lần mở app** — khởi động chậm 10–20 giây và bị nhiều phần mềm diệt virus chặn.
One-folder nén ZIP khởi động gần như tức thì.

## Dữ liệu người dùng

App **chỉ** ghi vào `%APPDATA%\HungPhatAccounting\`:

- `ketoan.db` — toàn bộ sổ kế toán (SQLite, chế độ WAL nên có thêm
  `ketoan.db-wal` / `ketoan.db-shm`)
- `einvoices\` — PDF hóa đơn điện tử đã tải về

Thư mục cài đặt chỉ chứa file chương trình. Vì vậy nâng cấp = ghi đè thư mục
cài đặt, dữ liệu giữ nguyên; gỡ cài đặt cũng không xóa sổ sách.

## Khi cập nhật cần nhớ

- Đổi `version` trong `pyproject.toml` → tên ZIP tự đổi theo;
  `version_info.txt` phải sửa tay cho khớp.
- Thêm thư viện mới đọc file dữ liệu → khai báo trong `datas` của `ketoan.spec`.
- Thêm migration `.sql` mới → tự động vào bản build (cả thư mục
  `data/migrations` được nhúng), không cần sửa gì.
- Thêm import chỉ xảy ra lúc runtime → thêm vào `hiddenimports`.

## Cảnh báo SmartScreen

File .exe chưa ký số nên Windows sẽ hiện "Windows protected your PC" ở lần chạy
đầu (bấm **More info → Run anyway**). Muốn bỏ hẳn cảnh báo này phải mua chứng
chỉ ký code (OV ~$200–400/năm, EV mới hết cảnh báo ngay lập tức).
