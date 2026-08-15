"""Sales documents (bán hàng): inventory OUT + revenue / VAT / COGS postings."""
from __future__ import annotations

from decimal import Decimal

from domain.models.invoice import Invoice, InvoiceKind
from domain.models.journal import JournalLine
from domain.models.partner import PartnerType
from domain.services.cogs_service import COGS_PROVISIONAL_NOTE
from domain.services.document_service import (
    DocumentService,
    DocumentValidationError,
)

# Backwards-compatible alias (callers/tests import SalesValidationError).
SalesValidationError = DocumentValidationError

_REVENUE_ACCOUNT = "511"
_VAT_OUTPUT_ACCOUNT = "3331"
_COGS_ACCOUNT = "632"

_ZERO = Decimal("0")


class SalesService(DocumentService):
    KIND = InvoiceKind.SALE
    PARTNER_TYPE = PartnerType.CUSTOMER

    def _apply_posting(self, invoice: Invoice) -> None:
        self._clear_side_effects(invoice)

        default_debit = invoice.payment_method.debit_account
        # Mỗi dòng tự định khoản: TK Nợ (tiền/phải thu) và TK Có (doanh thu) lấy
        # theo dòng → đầu chứng từ → mặc định. TK kho (line.account_code) vừa
        # định tuyến việc xuất kho, vừa là TK ghi Có của giá vốn.
        #
        # GIÁ VỐN ghi NGAY lúc bán theo đơn giá bình quân tại thời điểm xuất, để
        # tài khoản kho (155/156…) có phát sinh Có đúng ngày bán và lên được Sổ
        # cái / Cân đối kế toán. Cuối kỳ CogsService định giá lại theo bình quân
        # CUỐI kỳ rồi ghi **phần chênh lệch** (KC-GV), nên lương công nhân về trễ
        # vẫn vào đủ giá vốn mà số đã ghi lúc bán không bị bỏ quên.
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
                item_name=line.item_name, unit=line.unit,
            )
            debit_account = (
                line.debit_account or invoice.debit_account or default_debit
            )
            revenue_account = (
                line.credit_account or invoice.credit_account or _REVENUE_ACCOUNT
            )
            debit_by_account[debit_account] = (
                debit_by_account.get(debit_account, _ZERO) + line.total
            )
            revenue_by_account[revenue_account] = (
                revenue_by_account.get(revenue_account, _ZERO) + line.amount
            )
            stock_account = movement.account_code.strip()
            cost = movement.quantity * movement.unit_cost
            if stock_account and cost > _ZERO:
                cogs_by_account[stock_account] = (
                    cogs_by_account.get(stock_account, _ZERO) + cost
                )

        lines: list[JournalLine] = []
        # Doanh thu: Nợ tiền/phải thu (theo dòng)  /  Có doanh thu + thuế GTGT đầu
        # ra. Dòng phải thu/tiền gắn mã khách hàng để theo dõi công nợ 131.
        for account, value in sorted(debit_by_account.items()):
            lines.append(self._line(account, debit=value,
                                    partner_code=invoice.partner_code))
        for account, value in sorted(revenue_by_account.items()):
            lines.append(self._line(account, credit=value))
        if invoice.vat_total > 0:
            lines.append(self._line(_VAT_OUTPUT_ACCOUNT, credit=invoice.vat_total))

        # Giá vốn: Nợ 632 / Có TK kho — tự cân đối nên bút toán vẫn khớp Nợ = Có.
        cogs_total = sum(cogs_by_account.values(), _ZERO)
        if cogs_total > _ZERO:
            lines.append(self._cogs_line(_COGS_ACCOUNT, debit=cogs_total))
            for account, value in sorted(cogs_by_account.items()):
                lines.append(self._cogs_line(account, credit=value))

        self._journal_entry(invoice, lines, desc=f"Bán hàng {invoice.ref}")

    def _cogs_line(
        self, code: str, *, debit: Decimal = _ZERO, credit: Decimal = _ZERO
    ) -> JournalLine:
        """Dòng giá vốn tạm tính — đánh dấu bằng diễn giải để cuối kỳ đối chiếu."""
        line = self._line(code, debit=debit, credit=credit)
        line.description = COGS_PROVISIONAL_NOTE
        return line
