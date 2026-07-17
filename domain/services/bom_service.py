"""Service for định mức (bill of materials).

Stores one product's material norms and, for the costing worksheet, computes a
product's direct-material cost (NVL, 15401) from its BOM:

    material_cost = Σ_material  quantity_per × produced_qty × unit_cost(material)

``unit_cost`` defaults to the inventory weighted-average; when a material has no
stock movements yet it falls back to the item's catalog ``unit_price``.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable, Iterable

from data.repositories.bom_repo import BomRepository
from data.repositories.inventory_repo import InventoryRepository
from data.repositories.item_repo import ItemRepository
from domain.models.bom import Bom, BomLine
from domain.services.inventory_service import InventoryService

_ZERO = Decimal("0")


class BomService:
    def __init__(
        self,
        repo: BomRepository | None = None,
        inventory: InventoryService | None = None,
        item_repo: ItemRepository | None = None,
    ) -> None:
        self._repo = repo or BomRepository()
        self._inventory = inventory or InventoryService(
            InventoryRepository(), ItemRepository()
        )
        self._items = item_repo or ItemRepository()

    # ----- persistence -----------------------------------------------------

    def load(self, product_code: str) -> Bom:
        lines = self._repo.list_for_product(product_code)
        for ln in lines:
            item = self._items.find_by_code(ln.material_code)
            if item:
                ln.material_name = item.name
                ln.unit = item.unit
        return Bom(product_code=product_code, lines=lines)

    def save(self, product_code: str, lines: list[BomLine]) -> None:
        kept = [ln for ln in lines if not ln.is_empty]
        for ln in kept:
            ln.product_code = product_code
        self._repo.replace_for_product(product_code, kept)

    def products(self) -> list[str]:
        return self._repo.list_products()

    def has_bom(self, product_code: str) -> bool:
        """True khi thành phẩm đã khai định mức NVL (dùng để quyết định có tự
        tính cột NVL từ định mức hay để người dùng nhập tay)."""
        return bool(self._repo.list_for_product(product_code))

    # ----- costing integration ---------------------------------------------

    def material_cost(
        self,
        product_code: str,
        produced_qty: Decimal,
        unit_cost_fn: Callable[[str], Decimal] | None = None,
    ) -> Decimal:
        """Direct-material cost for *produced_qty* units of *product_code*."""
        cost_of = unit_cost_fn or self._default_unit_cost
        total = _ZERO
        for ln in self._repo.list_for_product(product_code):
            total += ln.quantity_per * produced_qty * cost_of(ln.material_code)
        return total

    def consumption_by_material(
        self,
        products: Iterable[tuple[str, Decimal]],
        unit_cost_fn: Callable[[str], Decimal] | None = None,
    ) -> dict[str, tuple[Decimal, Decimal]]:
        """Aggregate raw-material consumption across produced products.

        ``products`` is ``(product_code, produced_qty)`` pairs. For each the BOM
        gives ``quantity_per`` of every material; summed across products this is
        the total quantity of each material issued to production. The value is
        ``qty × unit_cost(material)`` so it matches the products' NVL column
        (Σ per-product material_cost == Σ per-material value).

        Returns ``{material_code: (qty, value)}``.
        """
        cost_of = unit_cost_fn or self._default_unit_cost
        qty_by: dict[str, Decimal] = {}
        for product_code, produced_qty in products:
            if produced_qty <= _ZERO:
                continue
            for ln in self._repo.list_for_product(product_code):
                mat = ln.material_code.strip()
                if not mat:
                    continue
                qty_by[mat] = qty_by.get(mat, _ZERO) + ln.quantity_per * produced_qty
        return {
            mat: (qty, qty * cost_of(mat))
            for mat, qty in qty_by.items()
            if qty > _ZERO
        }

    def _default_unit_cost(self, material_code: str) -> Decimal:
        avg = self._inventory.average_cost(material_code)
        if avg > _ZERO:
            return avg
        item = self._items.find_by_code(material_code)
        return item.unit_price if item else _ZERO
