"""Sales documents (bán hàng): inventory OUT + revenue / VAT / COGS postings."""
from __future__ import annotations

from decimal import Decimal

from domain.models.invoice import Invoice, InvoiceKind
from domain.models.journal import JournalLine
from domain.models.partner import PartnerType
from domain.services.document_service import (
    DocumentService,
    DocumentValidationError,
)

# Backwards-compatible alias (callers/tests import SalesValidationError).
SalesValidationError = DocumentValidationError

_REVENUE_ACCOUNT = "511"
_VAT_OUTPUT_ACCOUNT = "3331"
_COGS_ACCOUNT = "632"


class SalesService(DocumentService):
    KIND = InvoiceKind.SALE
    PARTNER_TYPE = PartnerType.CUSTOMER

    def _apply_posting(self, invoice: Invoice) -> None:
        self._clear_side_effects(invoice)

        default_debit = invoice.payment_method.debit_account
        # Mỗi dòng tự định khoản: TK Nợ (tiền/phải thu) và TK Có (doanh thu) lấy
        # theo dòng → đầu chứng từ → mặc định. TK kho (line.account_code) vẫn riêng,
        # định tuyến xuất kho + giá vốn (Có kho).
        debit_by_account: dict[str, Decimal] = {}
        revenue_by_account: dict[str, Decimal] = {}
        cogs_by_account: dict[str, Decimal] = {}
        for line in invoice.lines:
            if not line.item_code or line.quantity <= 0:
                continue
            movement = self._inventory.record_out(
                line.item_code, line.quantity,
                move_date=invoice.invoice_date, source_ref=invoice.ref,
                note=invoice.description, account_code=line.account_code,
                item_name=line.item_name,
            )
            stock_account = line.account_code or movement.account_code
            if stock_account and movement.value > 0:
                cogs_by_account[stock_account] = (
                    cogs_by_account.get(stock_account, Decimal("0")) + movement.value
                )
            debit_account = (
                line.debit_account or invoice.debit_account or default_debit
            )
            revenue_account = (
                line.credit_account or invoice.credit_account or _REVENUE_ACCOUNT
            )
            debit_by_account[debit_account] = (
                debit_by_account.get(debit_account, Decimal("0")) + line.total
            )
            revenue_by_account[revenue_account] = (
                revenue_by_account.get(revenue_account, Decimal("0")) + line.amount
            )

        lines: list[JournalLine] = []
        # Doanh thu: Nợ tiền/phải thu (theo dòng)  /  Có doanh thu (theo dòng) +
        # thuế GTGT đầu ra. Dòng phải thu/tiền gắn mã khách hàng để theo dõi công
        # nợ chi tiết (131); khách lẻ → partner_code rỗng, không tách đối tượng.
        for account, value in sorted(debit_by_account.items()):
            lines.append(self._line(account, debit=value,
                                    partner_code=invoice.partner_code))
        for account, value in sorted(revenue_by_account.items()):
            lines.append(self._line(account, credit=value))
        if invoice.vat_total > 0:
            lines.append(self._line(_VAT_OUTPUT_ACCOUNT, credit=invoice.vat_total))
        # Giá vốn: Nợ 632  /  Có kho (152/153/155/156).
        total_cogs = sum(cogs_by_account.values(), Decimal("0"))
        if total_cogs > 0:
            lines.append(self._line(_COGS_ACCOUNT, debit=total_cogs))
            for account, value in sorted(cogs_by_account.items()):
                lines.append(self._line(account, credit=value))

        self._journal_entry(invoice, lines, desc=f"Bán hàng {invoice.ref}")
