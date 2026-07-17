"""Bộ phân tích XML hóa đơn điện tử (HĐĐT) theo TT78/NĐ123-BTC.

Bóc dữ liệu có cấu trúc từ file XML ký số mà nhà cung cấp HĐĐT gửi kèm email:
số hóa đơn, ký hiệu, ngày, người bán/mua (tên · MST · địa chỉ) và danh sách hàng
hóa dịch vụ. Phòng thủ trước biến thể namespace / thiếu thẻ: tra cứu theo *tên thẻ
cục bộ* (bỏ namespace) và mọi field thiếu đều rơi về giá trị rỗng/0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET


class EInvoiceParseError(ValueError):
    """Không đọc được XML như một hóa đơn điện tử hợp lệ."""


@dataclass
class ParsedLine:
    name: str = ""
    unit: str = ""
    quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    unit_price: Decimal = field(default_factory=lambda: Decimal("0"))
    vat_rate: Decimal = field(default_factory=lambda: Decimal("0"))
    amount: Decimal = field(default_factory=lambda: Decimal("0"))


@dataclass
class ParsedInvoice:
    invoice_no: str = ""
    serial: str = ""          # ký hiệu hiển thị, vd "1C22TAA" (mẫu số + ký hiệu)
    invoice_date: date = field(default_factory=date.today)
    seller_name: str = ""
    seller_tax_code: str = ""
    seller_address: str = ""
    buyer_name: str = ""
    buyer_tax_code: str = ""
    buyer_address: str = ""
    currency: str = "VND"
    lines: list[ParsedLine] = field(default_factory=list)


# ----- tra cứu theo tên thẻ cục bộ (bỏ namespace) -----------------------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find(elem: ET.Element | None, name: str) -> ET.Element | None:
    """Phần tử con/cháu đầu tiên có tên cục bộ trùng (không phân biệt hoa thường)."""
    if elem is None:
        return None
    name = name.lower()
    for node in elem.iter():
        if node is elem:
            continue
        if _local(node.tag).lower() == name:
            return node
    return None


def _find_all(elem: ET.Element | None, name: str) -> list[ET.Element]:
    if elem is None:
        return []
    name = name.lower()
    return [n for n in elem.iter() if _local(n.tag).lower() == name and n is not elem]


def _text(elem: ET.Element | None, name: str) -> str:
    node = _find(elem, name)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _decimal(value: str) -> Decimal:
    """Parse số tiền/số lượng; bỏ dấu phân cách nghìn, chấp nhận rỗng → 0."""
    if not value:
        return Decimal("0")
    cleaned = value.strip().replace(" ", "")
    # Định dạng VN/quốc tế trộn lẫn: nếu có cả ',' và '.', dấu cuối là thập phân.
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Chỉ có ',' → coi là phân cách nghìn (HĐĐT chuẩn dùng '.' thập phân).
        cleaned = cleaned.replace(",", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _vat_rate(value: str) -> Decimal:
    """'10%' → 10; '0%' → 0; 'KCT'/'KKKNT' (không chịu/không kê khai) → 0."""
    if not value:
        return Decimal("0")
    cleaned = value.strip().rstrip("%").strip()
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _parse_date(value: str) -> date:
    if not value:
        return date.today()
    head = value.strip().replace("/", "-")[:10]
    try:
        return date.fromisoformat(head)
    except ValueError:
        return date.today()


# ----- API --------------------------------------------------------------------

def parse_einvoice(xml_bytes: bytes) -> ParsedInvoice:
    """Phân tích bytes XML HĐĐT → ParsedInvoice. Raise EInvoiceParseError nếu hỏng."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise EInvoiceParseError(f"XML không hợp lệ: {exc}") from exc

    common = _find(root, "TTChung")
    content = _find(root, "NDHDon")
    if common is None and content is None:
        raise EInvoiceParseError("Không phải hóa đơn điện tử (thiếu TTChung/NDHDon).")

    model_no = _text(common, "KHMSHDon")   # mẫu số, vd "1"
    symbol = _text(common, "KHHDon")        # ký hiệu, vd "C22TAA"
    seller = _find(content, "NBan")
    buyer = _find(content, "NMua")

    parsed = ParsedInvoice(
        invoice_no=_text(common, "SHDon"),
        serial=f"{model_no}{symbol}".strip(),
        invoice_date=_parse_date(_text(common, "NLap")),
        seller_name=_text(seller, "Ten"),
        seller_tax_code=_text(seller, "MST"),
        seller_address=_text(seller, "DChi"),
        buyer_name=_text(buyer, "Ten"),
        buyer_tax_code=_text(buyer, "MST"),
        buyer_address=_text(buyer, "DChi"),
        currency=_text(common, "DVTTe") or "VND",
    )

    goods = _find(content, "DSHHDVu")
    for item in _find_all(goods, "HHDVu"):
        name = _text(item, "THHDVu")
        if not name:
            continue
        quantity = _decimal(_text(item, "SLuong"))
        unit_price = _decimal(_text(item, "DGia"))
        amount = _decimal(_text(item, "ThTien"))
        # Một số HĐ chỉ ghi thành tiền — suy ra đơn giá khi có thể.
        if unit_price == 0 and quantity > 0 and amount > 0:
            unit_price = amount / quantity
        parsed.lines.append(
            ParsedLine(
                name=name,
                unit=_text(item, "DVTinh"),
                quantity=quantity,
                unit_price=unit_price,
                vat_rate=_vat_rate(_text(item, "TSuat")),
                amount=amount,
            )
        )

    return parsed
