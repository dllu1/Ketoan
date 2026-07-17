# Hưng Phát Accounting Suite

<samp>[Tiếng Việt](README.md) · **English** · [中文](README.zh.md) · [Français](README.fr.md)</samp>

A desktop accounting application for Vietnamese businesses, built with **Python + PySide6**.
It supports the **Circular 200** and **Circular 133** accounting regimes (switchable) and
stores everything locally in **SQLite** — no server required, runs entirely on the user's machine.

> In-app display name: *Hung Phat Accounting* — organization: *Hung Phat M&E*.

---

## Key features

| Module | Description |
|---|---|
| **Dashboard** | Overview: revenue/expenses, receivables/payables, trend charts, quick metrics. |
| **General journal** | Manual journal entries with per-line partner tagging (accounts 131/331). |
| **Directory** | Chart of accounts, customers/suppliers, items, warehouses. |
| **Sales / Purchases** | Output/input invoices that auto-generate journal entries and inventory movements. |
| **Cash** | Cash & bank receipt/payment vouchers with partner selection for receivables/payables. |
| **Inventory** | Goods received–issued–on-hand sheets for materials and **product costing** (allocated by material ratio). |
| **Fixed assets** | Fixed-asset register and depreciation. |
| **Tax** | VAT / corporate income tax returns, pre-filled with company details. |
| **Reports** | General ledger, detailed ledgers, trial balance, income statement; export to Excel/PDF. |
| **E-invoices** | Fetch invoices from email (IMAP), parse the XML into draft documents. |
| **Year-end closing** | Locks a fiscal year's data; auto-closes 48 hours after year-end if left untouched. |

### Fetching e-invoices from email

- Connects to the mailbox over **IMAP** with two authentication modes: **OAuth2 (XOAUTH2)**
  for Gmail, or **App Password / IMAP password** (Yahoo, custom IMAP).
- Parses **e-invoice XML in the TT78/Decree 123 standard** (tags `TTChung`, `NDHDon`,
  `NBan`, `NMua`, `DSHHDVu`…), compatible with most providers (Viettel, VNPT, MISA, BKAV…).
- Reads **XML compressed inside a `.zip`** too; any attached PDF is kept for reference.
- **Automatic sale/purchase classification by company tax code**: when the seller's tax code
  matches the company → **sales** invoice (partner = buyer); otherwise → **purchase**.
  - **Purchase** invoices usually land in `INBOX` (the e-invoice portal emails them to you).
  - **Sales** invoices you compose and email to customers live in `[Gmail]/Sent Mail`.
- The **"Rescan from start"** button resets the UID marker to re-scan the whole folder
  (duplicates are prevented by invoice number).

Detailed instructions are available in-app: **User Guide → "Automatically fetch e-invoices
(HĐĐT) from email"**.

---

## Requirements

- **Python ≥ 3.11**
- Windows (tested on Windows 11); should also run on any platform PySide6 supports.

## Install & run

```bash
# 1) Create a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

# 2) Install dependencies (including the report-export extras)
pip install -e ".[reports]"

# 3) Run the app
python main.py
```

To also install the testing tools: `pip install -e ".[dev,reports]"`.

### User data

The database and attachments are stored outside the source tree, at:

```
%APPDATA%\HungPhatAccounting\
├── ketoan.db          # all accounting data (SQLite)
└── einvoices\         # invoice PDFs downloaded from email
```

On first launch the app creates the database and seeds the chart of accounts.

### Demo data & reset

Under **Settings → Demo data**:
- **Load demo data** — generates a full year of figures to try things out.
- **Wipe all data** — start entering real figures (always keeps the chart of accounts
  and the selected circular).

---

## Project structure

```
Ketoan/
├── main.py                  # Entry point (QApplication + ChromeWindow)
├── app/                     # Config, theme, email poller, shortcuts
├── domain/                  # Pure-Python business logic (UI-independent)
│   ├── models/              #   Dataclasses: Invoice, Journal, Partner, Item…
│   └── services/            #   Logic: sales/purchases, inventory, costing, tax, e-invoice…
├── data/                    # Data layer
│   ├── database.py          #   Shared SQLite connection
│   ├── migrations/          #   *.sql that create/upgrade the schema in order
│   ├── repositories/        #   Per-table queries
│   └── email/               #   IMAP client + OAuth (e-invoice fetch)
├── ui/                      # PySide6 interface
│   ├── chrome/              #   Window shell, sidebar, status bar
│   ├── screens/             #   One screen per module
│   ├── modals/ primitives/  #   Dialogs & reusable widgets
│   └── resources/           #   QSS, fonts, icons
├── reports/exporters/       # Export to Excel (openpyxl) / PDF (reportlab)
└── tests/                   # pytest (domain, data, reports, ui)
```

### Architecture

A clear layering: **UI → domain services → repositories → SQLite**. The `domain` layer
does not import PySide6, so it can be tested independently without a GUI. All SQLite work
goes through one shared connection on the main thread; network tasks (IMAP) run in a
`QThread` and hand results back to the main thread for safe DB writes.

---

## Database

The schema is managed by files in `data/migrations/` (named `NNN_name.sql`), run in order
at startup. Add schema changes by creating a new migration file with the next number —
do not edit already-released files.

## Testing

```bash
python -m pytest --basetemp=.pytest_tmp
```

> ⚠️ On Windows the `--basetemp=.pytest_tmp` flag is required, otherwise tests that use a
> temp directory hit permission errors.

Tests focus on the `domain`/`data` layers (no GUI needed). E-invoice-related examples:
`tests/domain/test_einvoice_parser.py`, `tests/domain/test_invoice_import_service.py`,
`tests/domain/test_email_config_service.py`, `tests/data/test_imap_client.py`.

---

## Development notes

- **Runtime dependencies**: `PySide6`, `google-auth`, `google-auth-oauthlib`
  (see `pyproject.toml`). Optional groups: `reports` (openpyxl, reportlab),
  `dev` (pytest, pytest-qt).
- **Posting model**: locking is done via **year-end closing** rather than per-document locks.
- **Local security**: passwords/OAuth tokens are only base64-*obfuscated* in the `settings`
  table — this is a personal machine, not a real security boundary (an OS keyring is out of
  scope for now).
