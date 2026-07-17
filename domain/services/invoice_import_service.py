"""InvoiceImportService: lấy HĐĐT từ email → tạo chứng từ nháp (DRAFT).

Tách hai pha rõ ràng để an toàn luồng:
  * ``fetch_parsed`` — CHỈ mạng (IMAP + phân tích XML), chạy được trong QThread.
  * ``persist``      — CHỈ ghi DB, phải chạy trên main thread (GUI).
``run`` gộp cả hai cho nút bấm thủ công.

Phân loại bán/mua theo MST công ty (CompanyService): MST người bán == MST công ty
→ SALE (đối tác = người mua); MST người mua == MST công ty → PURCHASE (đối tác =
người bán); không khớp → mặc định PURCHASE (hóa đơn đầu vào).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.config import USER_DATA_DIR
from data.email import imap_client
from data.repositories.invoice_repo import InvoiceRepository
from data.repositories.item_repo import ItemRepository
from data.repositories.partner_repo import PartnerRepository
from domain.models.invoice import (
    Invoice,
    InvoiceKind,
    InvoiceLine,
    InvoiceStatus,
    PaymentMethod,
)
from domain.services.company_service import CompanyService
from domain.services.document_service import DocumentService, DocumentValidationError
from domain.services.einvoice_parser import (
    EInvoiceParseError,
    ParsedInvoice,
    parse_einvoice,
)
from domain.services.email_config_service import EmailConfig, EmailConfigService
from domain.services.purchase_service import PurchaseService
from domain.services.sales_service import SalesService

_PDF_DIR = USER_DATA_DIR / "einvoices"
_DEFAULT_PURCHASE_STOCK = "156"


@dataclass
class ParsedEmailInvoice:
    """Một HĐĐT đã bóc khỏi email (chưa ghi DB)."""
    parsed: ParsedInvoice
    uid: int = 0
    pdf_bytes: bytes | None = None
    pdf_filename: str = ""


@dataclass
class ImportResult:
    imported: int = 0
    skipped: int = 0
    unknown_partner: int = 0
    errors: list[str] = field(default_factory=list)


def _digits(value: str) -> str:
    """MST so khớp: chỉ giữ chữ số (bỏ khoảng trắng, gạch nối)."""
    return re.sub(r"\D", "", value or "")


def _slug_code(name: str) -> str:
    """Sinh mã tạm cho mặt hàng/đối tác chưa có — để chứng từ nháp hợp lệ."""
    cleaned = re.sub(r"[^0-9A-Za-zÀ-ỹ]+", "", (name or "").upper())
    return cleaned[:20] or "TMP"


def _safe_filename(ref: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "_", ref) or "invoice"


class InvoiceImportService:
    def __init__(
        self,
        *,
        sales: SalesService | None = None,
        purchase: PurchaseService | None = None,
        company: CompanyService | None = None,
        partner_repo: PartnerRepository | None = None,
        invoice_repo: InvoiceRepository | None = None,
        item_repo: ItemRepository | None = None,
        email_config: EmailConfigService | None = None,
    ) -> None:
        # Cho phép inject (test) hoặc tự dựng mặc định như SalesScreen/PurchaseScreen.
        if sales is None or purchase is None:
            from data.repositories.account_repo import AccountRepository
            from data.repositories.inventory_repo import InventoryRepository
            from data.repositories.journal_repo import JournalRepository
            from domain.services.inventory_service import InventoryService
            from domain.services.journal_service import JournalService

            inv_repo = invoice_repo or InvoiceRepository()
            inventory = InventoryService(InventoryRepository(), ItemRepository())
            journal = JournalService(JournalRepository())
            partners = partner_repo or PartnerRepository()
            accounts = AccountRepository()
            sales = sales or SalesService(inv_repo, inventory, journal, partners, accounts)
            purchase = purchase or PurchaseService(
                inv_repo, inventory, journal, partners, accounts
            )
        self._sales = sales
        self._purchase = purchase
        self._company = company or CompanyService()
        self._partners = partner_repo or PartnerRepository()
        self._invoices = invoice_repo or InvoiceRepository()
        self._items = item_repo or ItemRepository()
        self._email_config = email_config or EmailConfigService()

    # ----- pha 1: mạng (chạy được trong thread) ----------------------------

    def fetch_parsed(self, config: EmailConfig) -> tuple[list[ParsedEmailInvoice], int]:
        """IMAP lấy thư mới + phân tích XML. Trả về (danh sách, UID cao nhất)."""
        messages = imap_client.fetch_invoice_messages(config, config.last_uid)
        items: list[ParsedEmailInvoice] = []
        max_uid = config.last_uid
        for msg in messages:
            max_uid = max(max_uid, msg.uid)
            if msg.xml_bytes is None:
                continue
            try:
                parsed = parse_einvoice(msg.xml_bytes)
            except EInvoiceParseError:
                continue  # đính kèm XML không phải hóa đơn → bỏ qua
            items.append(
                ParsedEmailInvoice(
                    parsed=parsed,
                    uid=msg.uid,
                    pdf_bytes=msg.pdf_bytes,
                    pdf_filename=msg.pdf_filename,
                )
            )
        return items, max_uid

    # ----- pha 2: ghi DB (main thread) -------------------------------------

    def persist(self, items: list[ParsedEmailInvoice]) -> ImportResult:
        result = ImportResult()
        company_tax = _digits(self._company.load().tax_code)
        name_to_item = {i.name.strip().lower(): i for i in self._items.list_all()}

        for item in items:
            invoice, service = self._build_invoice(item, company_tax, name_to_item)
            if self._invoices.find_by_ref(invoice.ref) is not None:
                result.skipped += 1
                continue
            self._save_pdf(item, invoice)
            try:
                service.create(invoice, save_new_partner=False)
            except DocumentValidationError as exc:
                if "đã tồn tại" in str(exc):
                    result.skipped += 1
                else:
                    result.errors.append(f"{invoice.ref}: {exc}")
                continue
            result.imported += 1
            if service.partner_is_unknown(invoice):
                result.unknown_partner += 1
        return result

    # ----- nút bấm thủ công: gộp cả hai pha --------------------------------

    def run(self) -> ImportResult:
        config = self._email_config.load()
        if not config.is_ready:
            from data.email.imap_client import EmailFetchError

            raise EmailFetchError(
                "Chưa cấu hình email. Vào Cấu hình › Email / Hóa đơn điện tử."
            )
        items, max_uid = self.fetch_parsed(config)
        result = self.persist(items)
        if max_uid > config.last_uid:
            self._email_config.set_last_uid(max_uid)
        return result

    # ----- dựng chứng từ ---------------------------------------------------

    def _build_invoice(
        self,
        item: ParsedEmailInvoice,
        company_tax: str,
        name_to_item: dict,
    ) -> tuple[Invoice, DocumentService]:
        p = item.parsed
        seller_tax = _digits(p.seller_tax_code)

        if company_tax and seller_tax == company_tax:
            kind = InvoiceKind.SALE
            pname, ptax, paddr = p.buyer_name, p.buyer_tax_code, p.buyer_address
            service: DocumentService = self._sales
        else:
            # MST người mua == công ty → mua vào; không khớp MST nào → mặc định mua vào.
            kind = InvoiceKind.PURCHASE
            pname, ptax, paddr = p.seller_name, p.seller_tax_code, p.seller_address
            service = self._purchase

        ref = self._make_ref(p, item.uid)
        partner_code = self._resolve_partner_code(ptax, pname)
        default_stock = _DEFAULT_PURCHASE_STOCK if kind is InvoiceKind.PURCHASE else ""

        invoice = Invoice(
            ref=ref,
            invoice_no=p.invoice_no,
            serial=p.serial,
            invoice_date=p.invoice_date,
            kind=kind,
            status=InvoiceStatus.DRAFT,
            payment_method=PaymentMethod.CREDIT,
            partner_code=partner_code,
            partner_name=pname,
            partner_tax_code=ptax,
            partner_address=paddr,
            description=f"HĐĐT {p.serial} số {p.invoice_no}".strip(),
            source="EMAIL",
            lines=[
                self._build_line(line, name_to_item, default_stock)
                for line in p.lines
            ],
        )
        return invoice, service

    @staticmethod
    def _build_line(line, name_to_item: dict, default_stock: str) -> InvoiceLine:
        match = name_to_item.get(line.name.strip().lower())
        # Khớp danh mục → dùng mã thật; chưa có → mã tạm để chứng từ nháp hợp lệ,
        # người dùng ánh xạ lại mặt hàng khi rà soát trước khi ghi sổ.
        item_code = match.code if match else _slug_code(line.name)
        account_code = (match.account_code if match else "") or default_stock
        return InvoiceLine(
            item_code=item_code,
            item_name=line.name,
            unit=line.unit,
            quantity=line.quantity,
            unit_price=line.unit_price,
            vat_rate=line.vat_rate,
            account_code=account_code,
        )

    def _resolve_partner_code(self, tax_code: str, name: str) -> str:
        """Khớp đối tác theo MST → dùng mã sẵn có; chưa có → mã tạm (báo đỏ sau)."""
        existing = self._partners.find_by_tax_code(tax_code)
        if existing is not None:
            return existing.code
        if tax_code.strip():
            return _digits(tax_code)
        return _slug_code(name)

    @staticmethod
    def _make_ref(parsed: ParsedInvoice, uid: int) -> str:
        base = f"{parsed.serial}-{parsed.invoice_no}".strip("-")
        return base or f"EMAIL-{uid}"

    def _save_pdf(self, item: ParsedEmailInvoice, invoice: Invoice) -> None:
        if not item.pdf_bytes:
            return
        try:
            _PDF_DIR.mkdir(parents=True, exist_ok=True)
            path = _PDF_DIR / f"{_safe_filename(invoice.ref)}.pdf"
            path.write_bytes(item.pdf_bytes)
            invoice.attachment_path = str(path)
        except OSError:
            invoice.attachment_path = ""  # lỗi ghi PDF không chặn việc nhập HĐ
