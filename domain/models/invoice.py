"""Invoice / InvoiceLine: hóa đơn bán hàng (chứng từ) theo system_routing.png.

A sales invoice is the *document* received/issued for a transaction. Posting it
drives two side-effects in the engine: inventory OUT movements (Xuất kho) and a
balanced journal entry (doanh thu + thuế GTGT + giá vốn).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class InvoiceKind(str, Enum):
    SALE = "SALE"            # Hóa đơn bán hàng (đầu ra)
    PURCHASE = "PURCHASE"    # Hóa đơn mua hàng (đầu vào)


class InvoiceStatus(str, Enum):
    DRAFT = "DRAFT"      # Nháp — chỉ lưu chứng từ, chưa ghi sổ/xuất kho
    POSTED = "POSTED"    # Đã ghi sổ — sinh bút toán + xuất kho


class PaymentMethod(str, Enum):
    """Hình thức thanh toán → tài khoản tiền/công nợ của bút toán."""
    CASH = "CASH"        # Tiền mặt → 111
    BANK = "BANK"        # Chuyển khoản → 112
    CREDIT = "CREDIT"    # Công nợ → 131 (phải thu) / 331 (phải trả)

    @property
    def debit_account(self) -> str:
        """Tài khoản Nợ cho bút toán bán hàng (phải thu / tiền)."""
        return {self.CASH: "111", self.BANK: "112", self.CREDIT: "131"}[self]

    @property
    def payable_account(self) -> str:
        """Tài khoản Có cho bút toán mua hàng (phải trả / tiền)."""
        return {self.CASH: "111", self.BANK: "112", self.CREDIT: "331"}[self]


@dataclass
class InvoiceLine:
    item_code: str
    item_name: str = ""
    unit: str = ""
    quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    unit_price: Decimal = field(default_factory=lambda: Decimal("0"))
    vat_rate: Decimal = field(default_factory=lambda: Decimal("10"))
    account_code: str = ""   # TK kho (152/153/155/156) — dùng cho giá vốn + xuất kho
    # Định khoản Nợ/Có riêng từng dòng (mỗi mặt hàng có thể vào một TK khác nhau).
    # Rỗng = kế thừa định khoản đầu chứng từ (Invoice.debit_account/credit_account)
    # rồi tới mặc định theo loại chứng từ / hình thức thanh toán.
    debit_account: str = ""
    credit_account: str = ""
    line_no: int = 0
    id: int | None = None
    invoice_id: int | None = None

    @property
    def amount(self) -> Decimal:
        """Thành tiền trước thuế."""
        return self.quantity * self.unit_price

    @property
    def vat_amount(self) -> Decimal:
        return (self.amount * self.vat_rate / Decimal("100")).quantize(Decimal("1"))

    @property
    def total(self) -> Decimal:
        return self.amount + self.vat_amount


@dataclass
class Invoice:
    ref: str                              # số chứng từ nội bộ (unique)
    invoice_no: str = ""                  # số hóa đơn GTGT
    serial: str = ""                      # ký hiệu / mẫu số
    invoice_date: date = field(default_factory=date.today)
    kind: InvoiceKind = InvoiceKind.SALE
    status: InvoiceStatus = InvoiceStatus.POSTED
    payment_method: PaymentMethod = PaymentMethod.CREDIT
    # Đối tác — denormalized so a guest (one-time) sale needs no directory record.
    partner_code: str = ""
    partner_name: str = ""
    partner_tax_code: str = ""
    partner_address: str = ""
    description: str = ""
    # Định khoản Nợ/Có (override; rỗng = dùng mặc định theo payment_method/kind).
    # SALE: debit = tiền/phải thu, credit = doanh thu (511).
    # PURCHASE: debit = kho mặc định, credit = phải trả/tiền.
    debit_account: str = ""
    credit_account: str = ""
    # Nguồn tạo chứng từ: "" = nhập tay, "EMAIL" = tự lấy từ hộp thư HĐĐT.
    source: str = ""
    # Đường dẫn PDF gốc lưu kèm khi nhập từ email (rỗng nếu nhập tay).
    attachment_path: str = ""
    lines: list[InvoiceLine] = field(default_factory=list)
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def subtotal(self) -> Decimal:
        return sum((line.amount for line in self.lines), Decimal("0"))

    @property
    def vat_total(self) -> Decimal:
        return sum((line.vat_amount for line in self.lines), Decimal("0"))

    @property
    def grand_total(self) -> Decimal:
        return self.subtotal + self.vat_total

    @property
    def is_guest(self) -> bool:
        """A one-time sale not tied to a directory partner code."""
        return not self.partner_code.strip()
