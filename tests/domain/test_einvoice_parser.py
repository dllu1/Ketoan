"""Tests cho bộ phân tích XML hóa đơn điện tử (einvoice_parser)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from domain.services.einvoice_parser import EInvoiceParseError, parse_einvoice

_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<HDon><DLHDon><TTChung>
  <KHMSHDon>1</KHMSHDon><KHHDon>C22TAA</KHHDon><SHDon>123</SHDon>
  <NLap>2026-06-18</NLap><DVTTe>VND</DVTTe>
</TTChung><NDHDon>
  <NBan><Ten>CONG TY BAN</Ten><MST>0312654987</MST><DChi>123 Le Loi</DChi></NBan>
  <NMua><Ten>CONG TY MUA</Ten><MST>0301234567</MST><DChi>45 Tran Hung Dao</DChi></NMua>
  <DSHHDVu>
    <HHDVu><STT>1</STT><THHDVu>Thep tam</THHDVu><DVTinh>Kg</DVTinh>
      <SLuong>100</SLuong><DGia>15000</DGia><ThTien>1500000</ThTien><TSuat>10%</TSuat></HHDVu>
    <HHDVu><STT>2</STT><THHDVu>Que han</THHDVu><DVTinh>Hop</DVTinh>
      <SLuong>5</SLuong><DGia>0</DGia><ThTien>500000</ThTien><TSuat>8%</TSuat></HHDVu>
  </DSHHDVu>
</NDHDon></DLHDon></HDon>"""


def test_parse_header_and_parties():
    p = parse_einvoice(_SAMPLE.encode("utf-8"))
    assert p.invoice_no == "123"
    assert p.serial == "1C22TAA"           # mẫu số + ký hiệu
    assert p.invoice_date == date(2026, 6, 18)
    assert p.seller_tax_code == "0312654987"
    assert p.buyer_tax_code == "0301234567"
    assert p.buyer_name == "CONG TY MUA"


def test_parse_lines_and_vat():
    p = parse_einvoice(_SAMPLE.encode("utf-8"))
    assert len(p.lines) == 2
    first = p.lines[0]
    assert first.name == "Thep tam"
    assert first.quantity == Decimal("100")
    assert first.unit_price == Decimal("15000")
    assert first.vat_rate == Decimal("10")   # "10%" → 10
    # Dòng 2 không ghi đơn giá → suy ra từ thành tiền / số lượng.
    assert p.lines[1].unit_price == Decimal("100000")
    assert p.lines[1].vat_rate == Decimal("8")


def test_namespaced_xml_is_tolerated():
    ns = _SAMPLE.replace("<HDon>", '<inv:HDon xmlns:inv="http://x">').replace(
        "</HDon>", "</inv:HDon>")
    p = parse_einvoice(ns.encode("utf-8"))
    assert p.invoice_no == "123"
    assert p.seller_tax_code == "0312654987"


def test_invalid_xml_raises():
    try:
        parse_einvoice(b"<nothing/>")
    except EInvoiceParseError:
        return
    raise AssertionError("Expected EInvoiceParseError")
