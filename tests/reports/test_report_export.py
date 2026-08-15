"""Sổ cái presentation + Excel/PDF export round-trip (no Qt).

Exercises ``build_general_ledger`` and the generic exporters end-to-end on a
synthetic ledger, so a report stays exportable as both .xlsx and .pdf. The PDF
case skips when reportlab is absent (optional ``[reports]`` extra).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from domain.models.report import (
    CashFlowStatement,
    GeneralLedger,
    GeneralLedgerAccount,
    GeneralLedgerRow,
    IncomeStatementB02,
    ReportPeriod,
)
from reports.report_tables import (
    build_cash_flow_statement,
    build_general_ledger,
    build_income_statement_b02,
)

_Z = Decimal("0")
_M = Decimal("1000000")


def _ledger() -> GeneralLedger:
    period = ReportPeriod(start=date(2026, 1, 1), end=date(2026, 3, 31))
    cash = GeneralLedgerAccount(
        code="111", name="Tiền mặt", opening_balance=200 * _M,
        rows=[
            GeneralLedgerRow(date(2026, 1, 15), "BH01", "Bán hàng",
                             "511", 100 * _M, _Z, 300 * _M),
            GeneralLedgerRow(date(2026, 3, 5), "CP01", "Chi phí văn phòng",
                             "642", _Z, 5 * _M, 295 * _M),
        ],
    )
    return GeneralLedger(period=period, accounts=[cash])


def test_build_general_ledger_document_shape():
    doc = build_general_ledger(_ledger())
    assert doc.title == "SỔ CÁI"
    assert len(doc.tables) == 1
    table = doc.tables[0]
    assert table.caption == "111 — Tiền mặt"
    assert [c.header for c in table.columns] == [
        "Ngày", "Số CT", "Diễn giải", "TK Đ/Ư", "Tên KH/NCC", "Nợ", "Có", "Số dư",
    ]
    # Opening-balance row followed by the two postings.
    assert len(table.rows) == 3
    assert table.rows[0][2] == "Số dư đầu kỳ"
    assert table.rows[0][7] == 200 * _M
    # Closing balance reported in the section's total row.
    assert table.total_row[-1] == 295 * _M


def test_export_excel_writes_readable_workbook(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from reports.exporters import export_excel

    out = tmp_path / "so_cai.xlsx"
    export_excel(build_general_ledger(_ledger()), out)
    assert out.exists() and out.stat().st_size > 0

    ws = openpyxl.load_workbook(out).active
    flat = [c.value for row in ws.iter_rows() for c in row]
    assert "SỔ CÁI" in flat
    assert "111 — Tiền mặt" in flat
    assert 295000000.0 in flat       # closing balance survives as a real number


def _b03() -> CashFlowStatement:
    period = ReportPeriod(start=date(2026, 1, 1), end=date(2026, 3, 31))
    prior = ReportPeriod(start=date(2025, 1, 1), end=date(2025, 3, 31))
    return CashFlowStatement(
        period=period,
        prior_period=prior,
        current={"01": 100 * _M, "02": -5 * _M, "20": 95 * _M,
                 "50": 95 * _M, "60": 200 * _M, "70": 295 * _M},
        prior={"01": 80 * _M, "20": 80 * _M, "50": 80 * _M, "70": 80 * _M},
    )


def test_build_cash_flow_statement_follows_b03_layout():
    doc = build_cash_flow_statement(_b03())
    assert doc.title == "BÁO CÁO LƯU CHUYỂN TIỀN TỆ (Mẫu số B03-DNN)"
    table = doc.tables[0]
    assert [c.header for c in table.columns] == [
        "Chỉ tiêu", "Mã số", "Thuyết minh", "Năm nay", "Năm trước",
    ]
    # Mã số in đúng cột, số chi mang dấu âm như mẫu in.
    by_code = {row[1]: row for row in table.rows if row[1]}
    assert by_code["01"][3] == 100 * _M
    assert by_code["01"][4] == 80 * _M
    assert by_code["02"][3] == -5 * _M
    # Dòng tiêu đề mục không có mã số và không có số liệu.
    assert table.rows[0][0].startswith("I. Lưu chuyển tiền")
    assert table.rows[0][1] == "" and table.rows[0][3] is None
    # [70] là dòng tổng cuối mẫu.
    assert table.total_row[1] == "70"
    assert table.total_row[3] == 295 * _M


def test_export_excel_writes_cash_flow_statement(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from reports.exporters import export_excel

    out = tmp_path / "b03.xlsx"
    export_excel(build_cash_flow_statement(_b03()), out)
    ws = openpyxl.load_workbook(out).active
    flat = [c.value for row in ws.iter_rows() for c in row]
    assert "BÁO CÁO LƯU CHUYỂN TIỀN TỆ (Mẫu số B03-DNN)" in flat
    assert 295000000.0 in flat
    assert -5000000.0 in flat


def test_build_income_statement_b02_follows_form_layout():
    period = ReportPeriod(start=date(2026, 1, 1), end=date(2026, 12, 31))
    prior = ReportPeriod(start=date(2025, 1, 1), end=date(2025, 12, 31))
    report = IncomeStatementB02(
        period=period, prior_period=prior,
        current={"01": 200 * _M, "10": 200 * _M, "40": -4 * _M, "60": 32 * _M},
        prior={"01": 150 * _M, "10": 150 * _M, "60": 20 * _M},
    )
    doc = build_income_statement_b02(report)
    assert doc.title == "BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH (Mẫu số B02-DNN)"
    table = doc.tables[0]
    assert [c.header for c in table.columns] == [
        "Chỉ tiêu", "Mã số", "Thuyết minh", "Năm nay", "Năm trước",
    ]
    by_code = {row[1]: row for row in table.rows if row[1]}
    assert by_code["01"][3] == 200 * _M
    assert by_code["01"][4] == 150 * _M
    assert by_code["40"][3] == -4 * _M           # lỗ khác giữ dấu âm
    # Mẫu kết thúc ở [60] lợi nhuận sau thuế, dựng thành dòng tổng.
    assert table.total_row[1] == "60"
    assert table.total_row[3] == 32 * _M
    # Mã số phải đủ và đúng thứ tự mẫu in.
    assert [row[1] for row in table.rows] + [table.total_row[1]] == [
        "01", "02", "10", "11", "20", "21", "22", "23", "24",
        "30", "31", "32", "40", "50", "51", "60",
    ]


def test_export_pdf_writes_file(tmp_path):
    pytest.importorskip("reportlab")
    from reports.exporters import export_pdf

    out = tmp_path / "so_cai.pdf"
    export_pdf(build_general_ledger(_ledger()), out)
    assert out.exists() and out.stat().st_size > 0
