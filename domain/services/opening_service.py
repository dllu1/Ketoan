"""Service for opening balances (số dư đầu kỳ) per fiscal year.

Two consumers read what this service stores:

* **Financial reports** — :meth:`account_openings` returns a net opening per
  account, which :class:`ReportService` adds as a baseline to its journal-derived
  opening so a period whose prior year has no postings still shows an opening.
* **NXT / sổ kho** — on :meth:`save`, the per-item stock detail lines (152/155/156)
  are pushed into the inventory ledger as ``OPENING`` movements dated the day
  before the fiscal year (so :meth:`InventoryService.compute_nxt` counts them as
  tồn đầu kỳ), under a per-year source key ``SDDK:<year>`` so re-saving refreshes
  rather than stacks.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from data.repositories.inventory_repo import InventoryRepository
from data.repositories.item_repo import ItemRepository
from data.repositories.opening_repo import OpeningBalanceRepository
from domain.models.inventory import InventoryMovement, MovementKind
from domain.models.opening import OpeningBalance
from domain.services.inventory_service import InventoryService

_SOURCE_PREFIX = "SDDK:"      # source tag for opening-balance movements
_ZERO = Decimal("0")
_ONE = Decimal("1")

# Stock accounts whose openings are detailed per item and pushed to the ledger.
_STOCK_ACCOUNTS = ("152", "153", "155", "156")


def _unit_cost(value: Decimal, qty: Decimal) -> Decimal:
    return (value / qty).quantize(_ONE) if qty else _ZERO


class OpeningBalanceService:
    def __init__(
        self,
        repo: OpeningBalanceRepository | None = None,
        inventory: InventoryService | None = None,
        item_repo: ItemRepository | None = None,
    ) -> None:
        self._repo = repo or OpeningBalanceRepository()
        self._inventory = inventory or InventoryService(
            InventoryRepository(), ItemRepository()
        )
        self._items = item_repo or ItemRepository()

    # ----- persistence -----------------------------------------------------

    def load(self, year: int) -> list[OpeningBalance]:
        return self._repo.list_for_year(year)

    def save(self, year: int, rows: list[OpeningBalance]) -> None:
        kept = [r for r in rows if not r.is_empty]
        for r in kept:
            r.fiscal_year = year
        self._repo.replace_for_year(year, kept)
        self._push_to_ledger(year, kept)

    # ----- report integration ----------------------------------------------

    def account_openings(self, year: int) -> dict[str, Decimal]:
        """Net opening (Nợ − Có) per account code for *year*.

        Stock detail lines contribute their value as a debit to the stock
        account, so 152/155/156 carry an opening even when only item detail was
        entered.
        """
        net: dict[str, Decimal] = {}
        for r in self._repo.list_for_year(year):
            net[r.account_code] = net.get(r.account_code, _ZERO) + r.net
        return net

    def baseline_before(self, before: date) -> dict[str, Decimal]:
        """Net opening per account for the fiscal year in effect by *before*.

        Only the **most recent** declared year with ``01/01/year <= before`` is
        used: the opening of year N already embeds everything up to the end of
        N−1, so summing multiple years would double-count. :class:`ReportService`
        adds this on top of its journal-derived opening.
        """
        in_effect = [r for r in self._repo.list_all() if date(r.fiscal_year, 1, 1) <= before]
        if not in_effect:
            return {}
        latest = max(r.fiscal_year for r in in_effect)
        net: dict[str, Decimal] = {}
        for r in in_effect:
            if r.fiscal_year == latest:
                net[r.account_code] = net.get(r.account_code, _ZERO) + r.net
        return net

    # ----- internals -------------------------------------------------------

    def _push_to_ledger(self, year: int, rows: list[OpeningBalance]) -> None:
        source = f"{_SOURCE_PREFIX}{year}"
        opening_date = date(year, 1, 1) - timedelta(days=1)  # đầu kỳ of year
        now = datetime.now()
        movements: list[InventoryMovement] = []
        for r in rows:
            if not r.is_item_line or r.opening_qty <= _ZERO:
                continue
            item = self._items.find_by_code(r.item_code)
            name = item.name if item else ""
            account = r.account_code or (item.account_code if item else "")
            movements.append(InventoryMovement(
                item_code=r.item_code, item_name=name, account_code=account,
                move_date=opening_date, kind=MovementKind.OPENING,
                quantity=r.opening_qty,
                unit_cost=_unit_cost(r.opening_value, r.opening_qty),
                source_ref=source, note="Số dư đầu kỳ", created_at=now,
            ))
        self._inventory.replace_source_movements(source, movements)
