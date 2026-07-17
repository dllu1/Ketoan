"""Shared workflow for invoice-style documents (bán hàng / mua hàng).

Both sales and purchases follow system_routing.png: enter a document, reconcile
the partner against the directory, then on posting generate inventory movements
and a balanced journal entry. The differences (inbound vs outbound stock, the
exact postings, customer vs supplier) live in the concrete subclasses.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from data.repositories.account_repo import AccountRepository
from data.repositories.invoice_repo import InvoiceRepository
from data.repositories.partner_repo import PartnerRepository
from domain.models.invoice import Invoice, InvoiceKind, InvoiceStatus
from domain.models.journal import EntryStatus, JournalEntry, JournalLine
from domain.models.partner import Partner, PartnerType
from domain.services.closing_service import ClosingService
from domain.services.inventory_service import InventoryService
from domain.services.journal_service import JournalService

_FALLBACK_NAMES = {
    "111": "Tiền mặt",
    "112": "Tiền gửi ngân hàng",
    "131": "Phải thu của khách hàng",
    "331": "Phải trả cho người bán",
    "133": "Thuế GTGT được khấu trừ",
    "1331": "Thuế GTGT được khấu trừ của hàng hóa, dịch vụ",
    "333": "Thuế và các khoản phải nộp Nhà nước",
    "3331": "Thuế GTGT đầu ra phải nộp",
    "511": "Doanh thu bán hàng và cung cấp dịch vụ",
    "632": "Giá vốn hàng bán",
}


class DocumentValidationError(ValueError):
    pass


class DocumentService:
    KIND: InvoiceKind = InvoiceKind.SALE
    PARTNER_TYPE: PartnerType = PartnerType.CUSTOMER

    def __init__(
        self,
        invoice_repo: InvoiceRepository,
        inventory: InventoryService,
        journal: JournalService,
        partner_repo: PartnerRepository | None = None,
        account_repo: AccountRepository | None = None,
        closing: ClosingService | None = None,
    ) -> None:
        self._repo = invoice_repo
        self._inventory = inventory
        self._journal = journal
        self._partners = partner_repo or PartnerRepository()
        self._accounts = account_repo or AccountRepository()
        self._closing = closing

    @property
    def _closer(self) -> ClosingService:
        if self._closing is None:
            self._closing = ClosingService()
        return self._closing

    # ----- queries ---------------------------------------------------------

    def list_all(self) -> list[Invoice]:
        return self._repo.list_all(self.KIND)

    def search(self, query: str) -> list[Invoice]:
        return self._repo.search(query.strip(), self.KIND)

    def partner_exists(self, code: str) -> bool:
        return bool(code.strip()) and self._partners.find_by_code(code) is not None

    def partner_is_unknown(self, invoice: Invoice) -> bool:
        """Chứng từ có đối tác (không phải khách lẻ) nhưng chưa có trong danh mục.

        Đối chiếu theo mã trước, rồi theo MST — khớp một trong hai là đã biết.
        Dùng chung cho báo đỏ ở danh sách / modal và cho luồng nhập từ email.
        """
        if invoice.is_guest:
            return False
        if self._partners.find_by_code(invoice.partner_code) is not None:
            return False
        if self._partners.find_by_tax_code(invoice.partner_tax_code) is not None:
            return False
        return True

    # ----- commands --------------------------------------------------------

    def create(self, invoice: Invoice, *, save_new_partner: bool = False) -> Invoice:
        invoice.kind = self.KIND
        self._validate(invoice)
        self._closer.ensure_open(invoice.invoice_date)
        if self._repo.find_by_ref(invoice.ref):
            raise DocumentValidationError(f"Số chứng từ '{invoice.ref}' đã tồn tại.")
        self._sync_partner(invoice, save_new_partner=save_new_partner)
        invoice.created_at = datetime.now()
        invoice.updated_at = invoice.created_at
        saved = self._repo.insert(invoice)
        if saved.status is InvoiceStatus.POSTED:
            self._apply_posting(saved)
        return saved

    def update(self, invoice: Invoice, *, save_new_partner: bool = False) -> Invoice:
        if invoice.id is None:
            raise DocumentValidationError("Không thể cập nhật chứng từ chưa được lưu.")
        invoice.kind = self.KIND
        # No per-document lock anymore: a document stays editable all year and is
        # only frozen once its fiscal year is closed (chốt sổ cuối năm).
        self._validate(invoice)
        self._closer.ensure_open(invoice.invoice_date)
        self._sync_partner(invoice, save_new_partner=save_new_partner)
        invoice.updated_at = datetime.now()
        saved = self._repo.update(invoice)
        if saved.status is InvoiceStatus.POSTED:
            self._apply_posting(saved)
        else:
            # Hạ chứng từ đã ghi sổ về nháp (bấm "Lưu nháp" khi sửa): phải gỡ
            # bút toán + phát sinh kho của lần ghi sổ trước, nếu không sẽ mồ côi.
            self._clear_side_effects(saved)
        return saved

    def post(self, invoice: Invoice, *, save_new_partner: bool = False) -> Invoice:
        if invoice.status is InvoiceStatus.POSTED:
            return invoice
        invoice.status = InvoiceStatus.POSTED
        return self.update(invoice, save_new_partner=save_new_partner)

    def delete(self, invoice: Invoice) -> None:
        if invoice.id is None:
            raise DocumentValidationError("Không tìm thấy chứng từ.")
        self._closer.ensure_open(invoice.invoice_date)
        self._inventory.remove_source(invoice.ref)
        self._journal.delete_by_ref(invoice.ref)
        self._repo.delete(invoice.id)

    # ----- partner reconciliation (system_routing.png) ---------------------

    def _sync_partner(self, invoice: Invoice, *, save_new_partner: bool) -> None:
        if invoice.is_guest:
            return
        existing = self._partners.find_by_code(invoice.partner_code)
        if existing is not None:
            changed = False
            for attr, value in (
                ("name", invoice.partner_name),
                ("tax_code", invoice.partner_tax_code),
                ("address", invoice.partner_address),
            ):
                if value and getattr(existing, attr) != value:
                    setattr(existing, attr, value)
                    changed = True
            if changed:
                existing.updated_at = datetime.now()
                self._partners.update(existing)
            return
        if save_new_partner:
            self._partners.insert(
                Partner(
                    code=invoice.partner_code,
                    name=invoice.partner_name or invoice.partner_code,
                    type=self.PARTNER_TYPE,
                    tax_code=invoice.partner_tax_code,
                    address=invoice.partner_address,
                )
            )

    # ----- posting (overridden per document kind) --------------------------

    def _apply_posting(self, invoice: Invoice) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def _clear_side_effects(self, invoice: Invoice) -> None:
        """Make re-posting idempotent."""
        self._inventory.remove_source(invoice.ref)
        self._journal.delete_by_ref(invoice.ref)

    def _journal_entry(self, invoice: Invoice, lines: list[JournalLine], desc: str) -> None:
        self._journal.create(
            JournalEntry(
                ref=invoice.ref,
                entry_date=invoice.invoice_date,
                description=invoice.description or desc,
                status=EntryStatus.POSTED,
                lines=lines,
            )
        )

    def _line(
        self, code: str, *, debit: Decimal = Decimal("0"),
        credit: Decimal = Decimal("0"), partner_code: str = "",
    ) -> JournalLine:
        account = self._accounts.find_by_code(code)
        name = account.name if account else _FALLBACK_NAMES.get(code, "")
        return JournalLine(
            account_code=code, account_name=name, debit=debit, credit=credit,
            partner_code=partner_code,
        )

    # ----- validation ------------------------------------------------------

    @staticmethod
    def _validate(invoice: Invoice) -> None:
        if not invoice.ref.strip():
            raise DocumentValidationError("Số chứng từ là bắt buộc.")
        real_lines = [
            ln for ln in invoice.lines if ln.item_code.strip() or ln.quantity > 0
        ]
        if not real_lines:
            raise DocumentValidationError("Chứng từ phải có ít nhất một dòng hàng.")
        for line in real_lines:
            if not line.item_code.strip():
                raise DocumentValidationError("Mỗi dòng phải chọn mặt hàng.")
            if line.quantity <= 0:
                raise DocumentValidationError(
                    f"Số lượng dòng '{line.item_code}' phải lớn hơn 0."
                )
            if line.unit_price < 0:
                raise DocumentValidationError("Đơn giá không được âm.")
