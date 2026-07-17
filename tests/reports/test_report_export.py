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
    GeneralLedger,
    GeneralLedgerAccount,
    GeneralLedgerRow,
    ReportPeriod,
)
from reports.report_tables import build_general_ledger

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


def test_export_pdf_writes_file(tmp_path):
    pytest.importorskip("reportlab")
    from reports.exporters import export_pdf

    out = tmp_path / "so_cai.pdf"
    export_pdf(build_general_ledger(_ledger()), out)
    assert out.exists() and out.stat().st_size > 0
