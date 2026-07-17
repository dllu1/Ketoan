"""Purchase documents (mua hàng): inventory IN + input-VAT / payable postings."""
from __future__ import annotations

from decimal import Decimal

from domain.models.invoice import Invoice, InvoiceKind
from domain.models.journal import JournalLine
from domain.models.partner import PartnerType
from domain.services.document_service import (
    DocumentService,
    DocumentValidationError,
)

PurchaseValidationError = DocumentValidationError

_VAT_INPUT_ACCOUNT = "1331"


class PurchaseService(DocumentService):
    KIND = InvoiceKind.PURCHASE
    PARTNER_TYPE = PartnerType.SUPPLIER

    def _apply_posting(self, invoice: Invoice) -> None:
        self._clear_side_effects(invoice)

        default_payable = invoice.payment_method.payable_account
        # Mỗi dòng tự định khoản: TK Nợ (nơi hàng/chi phí ghi vào) và TK Có (phải
        # trả/tiền) lấy theo dòng → đầu chứng từ → mặc định. TK kho vẫn riêng để
        # định tuyến nhập–xuất–tồn; với hàng tồn kho thường trùng TK Nợ.
        debit_by_account: dict[str, Decimal] = {}
        credit_by_account: dict[str, Decimal] = {}
        for line in invoice.lines:
            if not line.item_code or line.quantity <= 0:
                continue
            stock_account = line.account_code or invoice.debit_account or "156"
            self._inventory.record_in(
                line.item_code, line.quantity, line.unit_price,
                move_date=invoice.invoice_date, source_ref=invoice.ref,
                note=invoice.description, account_code=stock_account,
                item_name=line.item_name,
            )
            debit_account = (
                line.debit_account or line.account_code
                or invoice.debit_account or "156"
            )
            credit_account = (
                line.credit_account or invoice.credit_account or default_payable
            )
            debit_by_account[debit_account] = (
                debit_by_account.get(debit_account, Decimal("0")) + line.amount
            )
            credit_by_account[credit_account] = (
                credit_by_account.get(credit_account, Decimal("0")) + line.total
            )

        lines: list[JournalLine] = []
        # Nợ kho/chi phí (theo từng dòng) + Nợ thuế GTGT đầu vào  /  Có phải trả/tiền.
        # Dòng phải trả/tiền gắn mã NCC để theo dõi công nợ chi tiết (331); NCC
        # vãng lai → partner_code rỗng, không tách đối tượng.
        for account, value in sorted(debit_by_account.items()):
            lines.append(self._line(account, debit=value))
        if invoice.vat_total > 0:
            lines.append(self._line(_VAT_INPUT_ACCOUNT, debit=invoice.vat_total))
        for account, value in sorted(credit_by_account.items()):
            lines.append(self._line(account, credit=value,
                                    partner_code=invoice.partner_code))

        self._journal_entry(invoice, lines, desc=f"Mua hàng {invoice.ref}")
