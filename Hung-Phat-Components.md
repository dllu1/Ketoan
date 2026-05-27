# Hưng Phát · Accounting Suite — Components Library

> Hệ thống component sử dụng để xây dựng giao diện phần mềm kế toán Hưng Phát M&E.
> Tông màu chủ đạo: `#a1caff` · Font: `JetBrains Mono` · Dark-mode by default.

---

## 1. Design Tokens

### Màu sắc · Color tokens

| Token | Giá trị | Sử dụng |
|---|---|---|
| `--brand` | `#a1caff` | Màu thương hiệu chính |
| `--brand-300` → `--brand-900` | OKLCH scale | Hover, border, accent variations |
| `--good` | `oklch(0.78 0.13 155)` | Trạng thái thành công, đã ghi sổ, đã thu |
| `--warn` | `oklch(0.82 0.13 75)` | Cảnh báo, chờ duyệt |
| `--bad` | `oklch(0.72 0.16 25)` | Lỗi, quá hạn, hủy bỏ |
| `--bg` | `#0b1018` (dark) / `#eef2f8` (light) | Nền ứng dụng |
| `--panel` | `#121925` / `#ffffff` | Nền sidebar, topbar |
| `--card` | `#161e2c` / `#ffffff` | Nền card |
| `--txt`, `--txt-2`, `--txt-3`, `--txt-4` | — | 4 cấp độ text |
| `--line`, `--line-strong`, `--line-soft` | — | Border tones |

### Typography

| Token | Giá trị |
|---|---|
| `--font` | `'JetBrains Mono', ui-monospace, monospace` |
| Cỡ chữ gốc | `13px` (cozy), `12.5px` (compact), `13.5px` (comfy) |
| Tabular numbers | `font-variant-numeric: tabular-nums` cho mọi số liệu |

### Layout

| Token | Giá trị | Ghi chú |
|---|---|---|
| `--radius` | `8px` (mặc định, tweakable 2–16px) | Bo góc chung |
| `--pad` | `16px` (cozy) | Padding chung |
| `--row-h` | `30px` (cozy) | Chiều cao hàng nav, table |
| `--kpi-pad` | `18px` (cozy) | Padding KPI card |
| `--border-strength` | `1` (tweakable 0–3) | Hệ số đậm border |

---

## 2. Window Chrome

### `<Chrome>`
Title bar kiểu cửa sổ Windows (PySide6 frameless), gồm:
- Brand mark (`HP`) + tên ứng dụng + version
- Menu bar ngang: Tệp · Hệ thống · Danh mục · Nghiệp vụ · Báo cáo · Tiện ích · Trợ giúp
- Breadcrumb hiển thị: phân hệ hiện tại · kỳ kế toán · công ty
- Window controls: minimize, maximize, close

**Props:** `here`, `children`, `onMin`, `onMax`, `onClose`, `onOpenMenu`

### `<StatusBar>`
Thanh trạng thái dưới cùng (nền brand `#a1caff`):
- Pill trạng thái kết nối (ONLINE)
- Thông tin sổ cái + kỳ kế toán
- Phím tắt nhanh (F1, F2, Ctrl+N, Ctrl+K)
- Pill user (initials + role)

**Props:** `user`, `info`, `ledger`

---

## 3. Navigation

### `<Sidebar>`
Sidebar trái, hỗ trợ 3 chế độ qua prop `layout`:
- `A` — đầy đủ nhãn VI/EN + phím tắt
- `B` — icon-only (compact 58px)
- `C` — đầy đủ + sub-rail phụ

Gồm: crest công ty, search box, list 9 phân hệ (icon + nhãn + badge thông báo + phím tắt), footer user.

**Props:** `active`, `onPick`, `layout`, `onSettings`

### `<TopBar>`
Top bar hybrid:
- Title phân hệ hiện tại (VI/EN)
- Search box lớn (Ctrl+K)
- Period picker (Kỳ kế toán)
- Primary action button (Bút toán mới)
- Icon buttons: Xuất Excel, In, Thông báo (có badge)
- User dropdown

**Props:** `here`, `here_en`, `onNew`, `onSearch`, `period`, `onPeriod`, `onBell`, `onUser`

### `<ModuleTabs>`
Tab bar ngang (chế độ Layout B), tab có icon + nhãn + count badge, active state với border dưới brand.

**Props:** `tabs`, `active`, `onPick`

### `<SubRail>`
Cột phụ thứ ba (Layout C, 200px), liệt kê sub-navigation cho phân hệ đang chọn.

**Props:** `items`, `active`, `onPick`, `title`

---

## 4. Primitives · UI cơ bản

### Buttons
| Class | Mô tả |
|---|---|
| `.btn` | Button gốc, h=28, padding 12, border + hover |
| `.btn.primary` | Nền brand `#a1caff`, text đậm |
| `.btn.ghost` | Trong suốt, chỉ hover background |
| `.btn.sm` | h=24, padding 8 |
| `.btn .kbd` | Phím tắt inline trong button |

### Badges & Status pills
| Class | Mô tả |
|---|---|
| `.badge` | Pill nhỏ uppercase, 4 biến thể: default, `.good`, `.warn`, `.bad`, `.brand` |
| `.status-pill` | Trạng thái: `.posted` (xanh), `.draft` (vàng), `.review` (xanh brand) |

### Keyboard
- `.kbd` — phím tắt standalone, viền dưới đậm, cỡ 10.5px

### Inputs
- `.input` — input wrapper với icon trái, h=28, focus ring brand
- Trong form: `.fld` chứa `.lbl` (uppercase 10px) + `.f` (input/select/textarea)

### Segmented control
- `.seg > button` — 2 mức background (off/on), border-radius nhẹ, dùng cho toggle xem biểu đồ

### Cards
- `.card` — container chung
- `.card-h` — header card (title + action)
- `.card-b` — body card

### Table
- `.tbl` — table gốc, head sticky, hover row, `.num` cho cột số, `.neg`/`.pos` cho âm/dương
- `.list-row` — list item dạng phẳng, có hover

### Filter chip
- `.filter-chip` — pill 26px tròn, active state nền brand-tint, có `.ct` count

### Empty state
- `.empty` — placeholder lớn cho module chưa build

---

## 5. Charts (SVG, viết tay)

### `<TrendChart>`
Line + area chart 12 tháng, có:
- Grid dashed
- Hover crosshair với tooltip
- 4 chế độ xem: `all` / `rev` / `cost` / `opex`
- Y-axis tự động format `tr`/`tỷ`

**Props:** `data`, `height`, `view`

### `<Donut>`
Donut chart monochrome (scale từ brand), legend song ngữ, tổng trung tâm.

**Props:** `data`, `size`

### `<AgedBars>`
Horizontal bars cho tuổi nợ, gradient từ brand → bad theo độ trễ.

**Props:** `data`, `height`

### `<Spark>`
Sparkline mini cho KPI card, 80×28, có dot cuối highlight.

**Props:** `data`, `w`, `h`, `positive`

---

## 6. Dashboard widgets

### `<KpiCard>`
Thẻ KPI: nhãn VI + EN, giá trị lớn tabular, delta % với arrow up/down, hint dòng dưới, sparkline góc phải.

**Props:** `k` (object), `sparkData` (number[])

### Alert strip
Thanh thông báo ngang full-width đầu dashboard, icon brand tròn + message + action button.

### Quick actions grid
6 nút lớn dạng card, mỗi nút có icon + tiêu đề VI + tagline EN + kbd phím tắt.

### Top customers list
Avatar số thứ tự + tên + mã + share bar + revenue/share %.

### Tax obligations list
Chỉ báo màu (`.tax-row.warn/.bad`) + tên VI/EN + hạn nộp + số tiền.

### Cash positions list
Badge mã TK + tên TK + amount tabular, hàng tổng có nền brand-tint.

---

## 7. Screens · Màn hình phân hệ

| Component | Mô tả |
|---|---|
| `<Dashboard>` | Tổng quan: 6 KPI + trend chart + donut + 5 widget |
| `<JournalScreen>` | Sổ nhật ký chung, mỗi bút toán có thể expand xem dòng Nợ/Có |
| `<SalesScreen>` | Hóa đơn bán hàng + 3 metric card + bảng có row-edit |
| `<InventoryScreen>` | Tồn kho 842 SKU + 3 metric + bảng có tiến độ tồn |
| `<PlaceholderScreen>` | Stub cho 5 phân hệ chưa build (Mua hàng, Quỹ, TSCĐ, BCTC, Thuế) |

### `<ScreenHeader>`
Toolbar đầu screen: title VI + EN + count badge + search + filter + xuất + in + primary add button (có phím tắt).

### `<FilterBar>`
Hàng filter chip với label uppercase + chips toggle + advanced filter + clear filter.

### `<ExpandedEntry>`
Hàng bút toán có thể expand, hiển thị 2 dòng con (Nợ / Có) với mã TK + tên TK + diễn giải + số tiền.

---

## 8. Modals · Pop-up

### `<EntryModal>` — Thêm bút toán
- Form metadata (loại phiếu, ngày, số CT, diễn giải)
- Bảng dòng bút toán có thể thêm/xóa
- Bar cân đối Nợ = Có, validate primary action
- Upload tệp đính kèm, ghi chú nội bộ
- Footer: phím tắt F2/Ctrl+S/Esc + Hủy + Lưu nháp + Ghi sổ

### `<InvoiceEditModal>` — Hóa đơn GTGT (mới / sửa)
- Form khách hàng + MST + hạn TT + HĐKT
- Bảng dòng hàng có VAT %
- Tổng kết: Subtotal + VAT + Total bằng chữ
- Mode `new` ẩn nút "Xóa hóa đơn"

### `<ItemModal>` — Mặt hàng kho (mới / sửa)
- Form đầy đủ: mã, tên, nhóm, ĐVT, TK kho, TK COGS, thuế, PP tính giá, giá vốn, giá bán, min/max, vị trí
- Mode `edit` thêm dashboard 4 metric: số lượng, giá trị, nhập/xuất MTD

### `<PartnerModal>` — Khách hàng / NCC (mới / sửa)
- Form: mã, tên, MST, loại tổ chức, hạn mức, địa chỉ, liên hệ, email, TK ngân hàng, TK kế toán mặc định
- Hiển thị công nợ hiện tại (edit mode)

### `<CashSlipModal>` — Phiếu thu / chi
- Form: ngày, số CT, người nộp/nhận, đối tượng, TK Nợ, TK Có, số tiền + bằng chữ, lý do, người duyệt

### `<ConfirmDialog>` — Xác nhận generic
- Title + message + 2 button (Hủy / Xác nhận), variant `danger` đỏ

### `<SearchPalette>` — Tìm nhanh (Ctrl+K)
- Floating palette 640px ở top
- 3 nhóm kết quả: Phân hệ, Tài khoản, Đối tượng
- Hint phím tắt ↑↓ ⏎ Esc

---

## 9. Popovers · Dropdown menu

### `<NotificationsPop>` — Chuông thông báo
- 380px, anchor bell button trong topbar
- Header: tiêu đề + badge "N MỚI"
- 6 mẫu thông báo: dot đỏ unread + icon màu (warn/bad/good) + title + body + meta + timestamp
- Footer: Đánh dấu đã đọc + Tất cả thông báo

### `<UserPop>` — User dropdown
- 280px, anchor user button
- Avatar lớn + tên + role + email
- 3 nhóm menu: Tài khoản · Hệ thống · Đăng xuất
- Menu item kiểu `.menu-i` có icon + label + (optional) phím tắt

### `<SettingsPop>` — Settings menu (sidebar gear)
- 240px, anchor bottom-left
- 3 nhóm: Danh mục · Tùy chỉnh · Dữ liệu
- 11 menu item

### `<PeriodPop>` — Period picker
- 320px, anchor period button
- Grid 12 tháng (4×3), active tháng hiện tại nền brand
- Hiển thị năm tài chính + trạng thái "ĐANG MỞ"

---

## 10. Icons

Set icon line 18px (stroke 1.5px, currentColor), vẽ tay từ paths cơ bản:

| Names |
|---|
| `grid` `book` `invoice` `cart` `box` `wallet` `cube` `chart` `tax` |
| `search` `bell` `plus` `minus` `check` `x` `filter` `download` `upload` `export` `print` `settings` |
| `chevron-down` `chevron-right` `chevron-left` `arrow-up` `arrow-down` |
| `calendar` `edit` `trash` `dot` `building` `sparkle` `user` `list` `menu` `min` `max` `close` |

**Usage:** `<Icon name="book" size={16} stroke={1.5}/>`

---

## 11. Tweaks · Tinh chỉnh

Panel bên phải (toggle qua toolbar):

| Section | Controls |
|---|---|
| **Brand** | Color swatches (6 màu), Dark mode toggle |
| **Layout** | Bố cục radio (A/B/C), Mật độ radio (compact/cozy/comfy) |
| **Typography** | Font select (JetBrains Mono / IBM Plex / Inter / Segoe UI) |
| **Hình khối** | Bo góc slider (2–16px), Đậm viền slider (0–3) |
| **Phím tắt nhanh** | Buttons mở các modal: Bút toán, Hóa đơn, Tìm nhanh, Phiếu thu/chi, Thêm KH, Thêm SKU |

---

## 12. Keyboard shortcuts

| Phím | Hành động |
|---|---|
| `F1` | Trợ giúp |
| `F2` → `F10` | Chuyển phân hệ (Tổng quan → Thuế) |
| `Ctrl + N` | Bút toán mới |
| `Ctrl + I` | Lập hóa đơn |
| `Ctrl + K` | Tìm nhanh |
| `Ctrl + S` | Lưu (trong form) |
| `Ctrl + P` | In |
| `Esc` | Đóng modal / palette |

---

## 13. Mock data

Toàn bộ mock data trong `data.jsx`:

| Dataset | Số dòng | Mô tả |
|---|---|---|
| `COMPANY` | — | Hồ sơ Hưng Phát M&E |
| `NAV` | 9 | Danh sách phân hệ |
| `MONTHLY` | 12 | Doanh thu/giá vốn/CP QL 12 tháng |
| `KPIS` | 6 | KPI dashboard |
| `RECENT_ENTRIES` | 8 | Nhật ký gần đây |
| `EXPENSE_MIX` | 6 | Cơ cấu chi phí |
| `TOP_CUSTOMERS` | 5 | Top KH |
| `AGED_AR` | 4 | Tuổi nợ phải thu |
| `CASH_ACCOUNTS` | 4 | Quỹ & ngân hàng |
| `TAX_ITEMS` | 4 | Nghĩa vụ thuế |
| `ACCOUNTS` | 14 | Chart of accounts (TT200) |
| `PARTNERS` | 5 | Khách hàng & NCC |
| `KEYBOARD_HINTS` | 7 | Phím tắt |

---

*Tài liệu này được sinh tự động từ source code của prototype.*
