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


# ----- chuẩn cũ của TCT (invoicexml/v1, mẫu 01GTKT) --------------------------

_SAMPLE_GDT2014 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<inv:invoice xmlns:inv="http://laphoadon.gdt.gov.vn/2014/09/invoicexml/v1">
<inv:invoiceData id="data">
  <inv:invoiceType>01GTKT</inv:invoiceType>
  <inv:templateCode>01GTKT0/001</inv:templateCode>
  <inv:invoiceSeries>AB/00E</inv:invoiceSeries>
  <inv:invoiceNumber>0000450</inv:invoiceNumber>
  <inv:invoiceIssuedDate>2026-01-15T00:00:00</inv:invoiceIssuedDate>
  <inv:currencyCode>VND</inv:currencyCode>
  <inv:sellerLegalName>CONG TY BAN</inv:sellerLegalName>
  <inv:sellerTaxCode>0100000000</inv:sellerTaxCode>
  <inv:sellerAddressLine>23 Duong so 7</inv:sellerAddressLine>
  <inv:buyerLegalName>CONG TY MUA</inv:buyerLegalName>
  <inv:buyerTaxCode>0200000000</inv:buyerTaxCode>
  <inv:buyerAddressLine>328 Dai Lo Binh Duong</inv:buyerAddressLine>
  <inv:items>
    <inv:item>
      <inv:lineNumber>1</inv:lineNumber>
      <inv:itemName>Ao ty 35kV sat</inv:itemName>
      <inv:unitName>cai</inv:unitName>
      <inv:quantity>1080.00</inv:quantity>
      <inv:unitPrice>3000</inv:unitPrice>
      <inv:itemTotalAmountWithoutVat>3240000</inv:itemTotalAmountWithoutVat>
      <inv:vatPercentage>10</inv:vatPercentage>
    </inv:item>
    <inv:item>
      <inv:lineNumber>2</inv:lineNumber>
      <inv:itemName>Ty TYT 870</inv:itemName>
      <inv:unitName>cay</inv:unitName>
      <inv:quantity>10.00</inv:quantity>
      <inv:unitPrice>0</inv:unitPrice>
      <inv:itemTotalAmountWithoutVat>770000</inv:itemTotalAmountWithoutVat>
      <inv:vatPercentage>10</inv:vatPercentage>
    </inv:item>
  </inv:items>
</inv:invoiceData></inv:invoice>"""


def test_parse_gdt2014_header_and_parties():
    p = parse_einvoice(_SAMPLE_GDT2014.encode("utf-8"))
    assert p.invoice_no == "0000450"
    assert p.serial == "AB/00E"        # ký hiệu kế toán ghi, không phải templateCode
    assert p.invoice_date == date(2026, 1, 15)  # cắt phần giờ "T00:00:00"
    assert p.seller_name == "CONG TY BAN"
    assert p.seller_tax_code == "0100000000"
    assert p.buyer_tax_code == "0200000000"
    assert p.currency == "VND"


def test_parse_gdt2014_lines():
    p = parse_einvoice(_SAMPLE_GDT2014.encode("utf-8"))
    assert len(p.lines) == 2
    first = p.lines[0]
    assert first.name == "Ao ty 35kV sat"
    assert first.unit == "cai"
    assert first.quantity == Decimal("1080.00")
    assert first.unit_price == Decimal("3000")
    assert first.amount == Decimal("3240000")
    assert first.vat_rate == Decimal("10")
    # Không ghi đơn giá → suy ra từ thành tiền / số lượng.
    assert p.lines[1].unit_price == Decimal("77000")


def test_invalid_xml_raises():
    try:
        parse_einvoice(b"<nothing/>")
    except EInvoiceParseError:
        return
    raise AssertionError("Expected EInvoiceParseError")
