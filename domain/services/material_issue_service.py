"""Post raw-material consumption (NVL xuất theo giá thành) to the 152 ledger.

The costing worksheet's direct-material column (NVL, 15401) is decomposed by
material code through each product's định mức (BOM). The resulting per-material
consumption is issued from account 152 as OUT movements under a per-period
source key (``GT-NVL:<period>``) so it appears in the Nhập–Xuất–Tồn report's
*Xuất* column for every material it touches — "trừ vào phần xuất của 152 theo
mã từng loại nguyên vật liệu".

Issue price follows the finished-goods rule (đơn giá xuất bình quân gia quyền):

    ĐG xuất = (TT tồn đầu kỳ + TT nhập) / (SL tồn đầu kỳ + SL nhập)

computed per material from the 152 ledger over the period. When a material has no
opening/nhập yet (chưa mua lần nào) it falls back to the catalog unit price so
the giá thành isn't silently zeroed.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from data.repositories.inventory_repo import InventoryRepository
from data.repositories.item_repo import ItemRepository
from domain.models.inventory import InventoryMovement, MovementKind
from domain.services.bom_service import BomService
from domain.services.inventory_service import InventoryService
from domain.services.material_sheet_service import _period_bounds, _unit_cost

_SOURCE_PREFIX = "GT-NVL:"        # nguồn cho phần xuất NVL theo giá thành
_MATERIAL_ACCOUNT = "152"
_ZERO = Decimal("0")
_ONE = Decimal("1")


class MaterialIssueService:
    def __init__(
        self,
        inventory: InventoryService | None = None,
        bom: BomService | None = None,
        item_repo: ItemRepository | None = None,
    ) -> None:
        self._inventory = inventory or InventoryService(
            InventoryRepository(), ItemRepository()
        )
        self._bom = bom or BomService()
        self._items = item_repo or ItemRepository()

    # ----- issue pricing ---------------------------------------------------

    def price_map(self, period_key: str) -> dict[str, Decimal]:
        """Weighted-average issue price per material (nhóm 152) for the period.

        Uses (TT đầu kỳ + TT nhập) / (SL đầu kỳ + SL nhập). OUT movements never
        affect this base, so the GT-NVL push we generate can't feed back into the
        price it was priced at.
        """
        start, end = _period_bounds(period_key)
        prices: dict[str, Decimal] = {}
        for r in self._inventory.compute_nxt(start, end):
            if r.account_code != _MATERIAL_ACCOUNT:
                continue
            base_qty = r.opening_qty + r.in_qty
            base_value = r.opening_value + r.in_value
            prices[r.item_code] = _unit_cost(base_value, base_qty)
        return prices

    def cost_fn(self, period_key: str):
        """A ``material_code -> unit_cost`` lookup: period weighted-average issue
        price, falling back to the catalog unit price when there's no stock yet.

        The costing view caches this once per reload to auto-fill the NVL column
        so what's shown equals what :meth:`post` later issues from 152.
        """
        prices = self.price_map(period_key)

        def cost_of(material_code: str) -> Decimal:
            price = prices.get(material_code, _ZERO)
            if price > _ZERO:
                return price
            item = self._items.find_by_code(material_code)
            return item.unit_price if item else _ZERO

        return cost_of

    # ----- consumption + posting ------------------------------------------

    def consumption(
        self, period_key: str, products: list[tuple[str, Decimal]]
    ) -> dict[str, tuple[Decimal, Decimal]]:
        """{material_code: (qty, value)} issued to produce *products* this period."""
        return self._bom.consumption_by_material(products, self.cost_fn(period_key))

    def post(
        self, period_key: str, products: list[tuple[str, Decimal]]
    ) -> dict[str, tuple[Decimal, Decimal]]:
        """Idempotently issue the period's NVL consumption from 152.

        Replaces any prior ``GT-NVL:<period>`` movements so re-saving giá thành
        refreshes the xuất rather than stacking it. Returns the consumption map.
        """
        consumed = self.consumption(period_key, products)
        self._push(period_key, consumed)
        return consumed

    def _push(
        self, period_key: str, consumed: dict[str, tuple[Decimal, Decimal]]
    ) -> None:
        source = _SOURCE_PREFIX + period_key
        start, _ = _period_bounds(period_key)
        now = datetime.now()
        movements: list[InventoryMovement] = []
        for material_code, (qty, value) in consumed.items():
            if qty <= _ZERO:
                continue
            item = self._items.find_by_code(material_code)
            name = item.name if item else ""
            account = (item.account_code if item else "") or _MATERIAL_ACCOUNT
            movements.append(InventoryMovement(
                item_code=material_code, item_name=name, account_code=account,
                move_date=start, kind=MovementKind.OUT, quantity=qty,
                unit_cost=_unit_cost(value, qty), source_ref=source,
                note="Xuất NVL theo giá thành", created_at=now,
            ))
        self._inventory.replace_source_movements(source, movements)
