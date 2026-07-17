# Hưng Phát 会计套件

<samp>[Tiếng Việt](README.md) · [English](README.en.md) · **中文** · [Français](README.fr.md)</samp>

面向越南企业的桌面会计软件，使用 **Python + PySide6** 开发。
支持 **第 200 号通知（TT200）** 与 **第 133 号通知（TT133）** 会计制度（可切换），
数据全部本地存储于 **SQLite** —— 无需服务器，完全在用户本机运行。

> 应用内显示名称：*Hung Phat Accounting* —— 单位：*Hung Phat M&E*。

---

## 主要功能

| 模块 | 说明 |
|---|---|
| **总览** | 仪表盘：收入/支出、应收/应付、趋势图、关键指标。 |
| **总日记账** | 手工录入分录，可按行标记往来对象（科目 131/331）。 |
| **基础目录** | 会计科目表、客户/供应商、存货、仓库。 |
| **销售 / 采购** | 销项/进项发票，自动生成分录并登记出入库。 |
| **资金** | 现金及银行收付款凭证，可为应收应付选择往来对象。 |
| **库存** | 原材料的入库–出库–结存表及**成本核算**（按材料比例分摊）。 |
| **固定资产** | 固定资产台账与折旧。 |
| **税务** | 增值税 / 企业所得税申报表，自动带入公司信息。 |
| **报表** | 总账、明细账、试算平衡表、利润表；可导出 Excel/PDF。 |
| **电子发票** | 从邮箱（IMAP）自动获取发票，解析 XML 生成草稿单据。 |
| **年末结账** | 锁定某会计年度数据；若无操作，年末 48 小时后自动结账。 |

### 从邮箱获取电子发票

- 通过 **IMAP** 连接邮箱，支持两种认证方式：Gmail 用 **OAuth2（XOAUTH2）**，
  或 **应用专用密码 / IMAP 密码**（Yahoo、自定义 IMAP）。
- 解析 **符合 TT78/第 123 号法令标准的电子发票 XML**（标签 `TTChung`、`NDHDon`、
  `NBan`、`NMua`、`DSHHDVu` 等），兼容大多数服务商（Viettel、VNPT、MISA、BKAV 等）。
- 也能读取 **压缩在 `.zip` 中的 XML**；随附的 PDF 会保留以供查阅。
- **按公司税号自动区分销售/采购**：卖方税号与公司一致 → **销售**发票（往来对象 = 买方）；
  否则 → **采购**发票。
  - **采购**发票通常进入 `INBOX`（电子发票平台发送到你的邮箱）。
  - 由你撰写邮件发给客户的 **销售**发票位于 `[Gmail]/Sent Mail`。
- **“从头重新扫描”** 按钮会重置 UID 标记以重新扫描整个文件夹（通过发票号去重，不会重复导入）。

详细说明见应用内：**使用指南 →「从邮箱自动获取电子发票（HĐĐT）」**。

---

## 系统要求

- **Python ≥ 3.11**
- Windows（已在 Windows 11 上测试）；也可在 PySide6 支持的其他平台运行。

## 安装与运行

```bash
# 1) 创建虚拟环境
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

# 2) 安装依赖（含报表导出可选组）
pip install -e ".[reports]"

# 3) 运行应用
python main.py
```

如需一并安装测试工具：`pip install -e ".[dev,reports]"`。

### 用户数据

数据库与附件存放在源码目录之外：

```
%APPDATA%\HungPhatAccounting\
├── ketoan.db          # 全部会计数据（SQLite）
└── einvoices\         # 从邮箱下载的发票 PDF
```

首次启动时，应用会自动创建数据库并预置会计科目表。

### 演示数据与清空

在 **设置 → 演示数据** 中：
- **载入演示数据** —— 生成整整一年的数据以供试用。
- **清空全部数据** —— 开始录入真实数据（始终保留会计科目表和当前所选通知制度）。

---

## 项目结构

```
Ketoan/
├── main.py                  # 入口（QApplication + ChromeWindow）
├── app/                     # 配置、主题、邮件轮询、快捷键
├── domain/                  # 纯 Python 业务逻辑（不依赖 UI）
│   ├── models/              #   数据类：Invoice、Journal、Partner、Item…
│   └── services/            #   逻辑：销售/采购、库存、成本、税务、电子发票…
├── data/                    # 数据层
│   ├── database.py          #   共享的 SQLite 连接
│   ├── migrations/          #   按顺序创建/升级 schema 的 *.sql
│   ├── repositories/        #   各表查询
│   └── email/               #   IMAP 客户端 + OAuth（获取电子发票）
├── ui/                      # PySide6 界面
│   ├── chrome/              #   窗口外壳、侧边栏、状态栏
│   ├── screens/             #   各模块界面
│   ├── modals/ primitives/  #   对话框与可复用组件
│   └── resources/           #   QSS、字体、图标
├── reports/exporters/       # 导出 Excel（openpyxl）/ PDF（reportlab）
└── tests/                   # pytest（domain、data、reports、ui）
```

### 架构

清晰的分层：**UI → 领域服务 → 仓储 → SQLite**。`domain` 层不导入 PySide6，
因此无需 GUI 即可独立测试。所有 SQLite 操作都通过主线程上的一个共享连接进行；
网络任务（IMAP）在 `QThread` 中运行，再把结果交回主线程以安全写库。

---

## 数据库

Schema 由 `data/migrations/` 中的文件管理（命名 `NNN_name.sql`），启动时按顺序执行。
新增 schema 变更时，请创建序号递增的新迁移文件 —— 不要修改已发布的旧文件。

## 测试

```bash
python -m pytest --basetemp=.pytest_tmp
```

> ⚠️ 在 Windows 上必须加 `--basetemp=.pytest_tmp` 参数，否则使用临时目录的测试会遇到权限错误。

测试集中在 `domain`/`data` 层（无需 GUI）。电子发票相关示例：
`tests/domain/test_einvoice_parser.py`、`tests/domain/test_invoice_import_service.py`、
`tests/domain/test_email_config_service.py`、`tests/data/test_imap_client.py`。

---

## 开发说明

- **运行时依赖**：`PySide6`、`google-auth`、`google-auth-oauthlib`
  （见 `pyproject.toml`）。可选组：`reports`（openpyxl、reportlab）、
  `dev`（pytest、pytest-qt）。
- **记账模型**：通过 **年末结账** 锁定，而非逐单据锁定。
- **本地安全**：密码/OAuth 令牌在 `settings` 表中仅做 base64 *混淆* ——
  这是个人电脑，并非真正的安全边界（操作系统钥匙串暂不在范围内）。
