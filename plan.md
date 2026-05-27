# Hưng Phát · Accounting Suite: Development & Implementation Plan

This document serves as the primary roadmap for the development team. It outlines the architectural design, data models, UI components, and the core operational workflows based on the system specifications.

---

## 1. Project Overview
A professional-grade accounting engine for **Hưng Phát M&E**, built with **PySide6**. It adheres to the **Circular 200/TT-BTC** (Vietnamese Accounting Standards) and features a high-density, dark-themed desktop interface.

---

## 2. Core Workflow: Sales & Document Processing
Based on `system_routing.png`, the application follows a specific logic for the **Sales (Bán hàng)** module:

### **Sales Entry Flow**
1.  **Initiate Sales**: Open the Sales module to record a transaction.
2.  **Input Documents**: Receive and enter document details (invoices, vouchers) from the customer.
3.  **System Validation**: The system checks if the customer already exists in the `Customer Directory`.
    *   **If Exists**: Save the transaction and update any changed customer metadata.
    *   **If NOT in System**: The system prompts: *"Save this customer to the directory?"*
        *   **Action: Save**: Creates a new record in `PartnerModal` + saves the document.
        *   **Action: Don't Save**: Saves the document as a one-time transaction (anonymous/guest) without creating a permanent record.

---

## 3. UI/UX Design (Frontend)

### **Visual Identity**
-   **Theme**: Deep Dark Mode (`#0b1018`).
-   **Typography**: `JetBrains Mono` for all data grids (tabular numbers enabled).
-   **Chrome**: `<Chrome>` (Frameless window with integrated title bar and menu).
-   **StatusBar**: `<StatusBar>` showing connection status, user role, and active ledger.

### **Navigation Modes**
-   **Mode A**: Full sidebar with text labels and shortcuts.
-   **Mode B**: Compact 58px icon-only rail with `<ModuleTabs>`.
-   **Mode C**: Nested tree for deep ledger navigation with `<SubRail>`.

### **Key Components**
-   `JournalScreen`: High-performance data grid for journal entries.
-   `EntryModal`: Balanced entry worksheet (Debit/Credit logic).
-   `SearchPalette`: Global `Ctrl + K` search overlay.
-   `TrendChart`: Multi-period financial trend visualization (12-month area chart).

---

## 4. Data Architecture (Backend)

The backend is structured around Python `dataclasses` defined in `data_structure.md`.

### **Core Data Structures**
-   `InvoiceData`: Tracks VAT invoices, serials, and tax rates (5%, 8%, 10%).
-   `JournalEntry`: The atomic unit of the General Journal (Debit/Credit).
-   `InventoryStock`: Manages the NXT (Nhập-Xuất-Tồn) for Materials (152), Goods (156), and Tools (153).
-   `FixedAsset`: Tracks depreciation (214) across a 12-month dynamic grid.
-   `LedgerAccount`: Maintains account balances (Initial, Period, Closing).

### **Financial Logic**
-   **Profit Calculation**: `Gross Revenue - COGS - Expenses = Pre-tax Profit`.
-   **Dynamic Tax Brackets**: CIT (Thuế TNDN) scales (15%, 17%, 20%) based on annual revenue thresholds (<15B, 15-50B, >50B VND).

---

## 5. Exporting & Reporting
The folder `Financial Reports and Ledgers/` contains the official templates and visual forms required for the **Export Function**. These images (`.jpg`) are the visual specifications for the final report outputs.

### **Implementation Requirements:**
-   **Mapping**: The system must map the internal `JournalEntry` and `LedgerAccount` data into the specific layouts found in the `.jpg` reference forms.
-   **Outputs**:
    *   **General Journal (Sổ nhật ký chung)**: Flat timeline of postings.
    *   **Trial Balance (Bảng cân đối tài khoản)**: Ensuring `Debit = Credit` accuracy.
    *   **BCTC (Financial Statements)**: Balance Sheet, P&L, and Cash Flow Statement.
-   **Format**: Primarily Excel/PDF export using the visual layouts in the reports folder as the structural guide.

---

## 6. Implementation Roadmap

### **Phase 1: Foundation**
-   Set up PySide6 frameless window environment using the `<Chrome>` component.
-   Implement the `Directory` system (Customers, Suppliers, Materials) using `PartnerModal` and `ItemModal`.

### **Phase 2: The Accounting Engine**
-   Build the `JournalEntry` processing logic and `JournalScreen`.
-   Implement the balanced entry validation in `EntryModal`.

### **Phase 3: Sales & Inventory**
-   Develop the workflow from `system_routing.png` (Sales Entry Flow).
-   Integrate NXT calculations for the four main inventory trackers (152, 153, 155, 156).

### **Phase 4: Reporting & Export**
-   Build the reporting engine to populate the forms in `Financial Reports and Ledgers/`.
-   Implement PDF/Excel export modules compliant with Circular 200.

---

## 7. Keyboard Shortcuts for Power Users
| Shortcut | Action |
| :--- | :--- |
| `F1` | Open Help Documentation |
| `F2 - F10` | Switch between Modules (Dashboard, Sales, etc.) |
| `Ctrl + N` | New Journal Entry (`EntryModal`) |
| `Ctrl + I` | New VAT Invoice (`InvoiceEditModal`) |
| `Ctrl + K` | Global Search Palette |
| `Ctrl + S` | Save / Post Transaction |
| `Ctrl + P` | Print Report |
| `Esc` | Close Modal / Cancel Action |
