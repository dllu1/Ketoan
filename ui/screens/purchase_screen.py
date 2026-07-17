"""PurchaseScreen: Mua hàng — purchase documents over the shared DocumentScreen."""
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
from domain.services.purchase_service import PurchaseService
from ui.screens.document_screen import DocumentScreen, DocumentScreenConfig


class PurchaseScreen(DocumentScreen):
    def __init__(self) -> None:
        inventory = InventoryService(InventoryRepository(), ItemRepository())
        journal = JournalService(JournalRepository())
        service = PurchaseService(
            InvoiceRepository(), inventory, journal,
            PartnerRepository(), AccountRepository(),
        )
        super().__init__(
            service,
            DocumentScreenConfig(
                kind=InvoiceKind.PURCHASE,
                title="Mua hàng",
                search_placeholder="Tìm số CT / số HĐ / nhà cung cấp…",
                new_label="Hóa đơn mua",
                new_icon="cart",
                partner_header="Nhà cung cấp",
                partner_noun="nhà cung cấp",
            ),
        )
