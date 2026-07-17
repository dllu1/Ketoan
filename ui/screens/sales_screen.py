"""SalesScreen: Bán hàng — sales documents over the shared DocumentScreen."""
from __future__ import annotations

from data.repositories.account_repo import AccountRepository
from data.repositories.inventory_repo import InventoryRepository
from data.repositories.invoice_repo import InvoiceRepository
from data.repositories.item_repo import ItemRepository
from data.repositories.journal_repo import JournalRepository
from data.repositories.partner_repo import PartnerRepository
from domain.models.invoice import InvoiceKind
from domain.services.inventory_service import InventoryService
from domain.services.journal_service import JournalService
from domain.services.sales_service import SalesService
from ui.screens.document_screen import DocumentScreen, DocumentScreenConfig


class SalesScreen(DocumentScreen):
    def __init__(self) -> None:
        inventory = InventoryService(InventoryRepository(), ItemRepository())
        journal = JournalService(JournalRepository())
        service = SalesService(
            InvoiceRepository(), inventory, journal,
            PartnerRepository(), AccountRepository(),
        )
        super().__init__(
            service,
            DocumentScreenConfig(
                kind=InvoiceKind.SALE,
                title="Bán hàng",
                search_placeholder="Tìm số CT / số HĐ / khách hàng…",
                new_label="Hóa đơn mới",
                new_icon="invoice",
                partner_header="Khách hàng",
                partner_noun="khách hàng",
                shortcut="Ctrl+I",
            ),
        )
