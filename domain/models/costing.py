"""Bảng tính giá thành sản phẩm (product-costing worksheet).

Costing method, taken from the blue field notes on the source form:

  * "Định mức → tính ra số tiền NVL của TP + Tương ứng + GCNK + CP khác" —
    a product's total cost (giá thành) is its direct material (NVL) plus three
    allocated pools: labor / tương ứng (15402), production overhead (154032)
    and other costs (154033).
  * "Tương ứng sp tính theo tỷ lệ NVL" — each non-material pool is split across
    products *in proportion to their direct-material amount*:

        allocated_pool_p = pool_total × (NVL_p / Σ NVL)

  * "1 cái = tổng giá thành / số lượng" — unit cost is the product's total cost
    divided by quantity produced.

Account map (sub-accounts of 154 — chi phí SXKD dở dang):
    15401 NVL trực tiếp · 15402 nhân công/tương ứng · 154032 SX chung · 154033 khác.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

_ZERO = Decimal("0")


@dataclass(frozen=True)
class CostPools:
    """The three non-material cost pools shared by the whole sheet.

    Mỗi pool đi kèm cờ ``*_manual``: người dùng đã tự gõ số vào ô đó hay chưa.
    Pool đã đánh dấu manual thì bảng giá thành giữ nguyên số của người dùng thay
    vì lấy lại từ sổ cái mỗi lần mở tab — xem ``CostingView._merge_pools``.
    """

    labor: Decimal = _ZERO       # 15402 — nhân công / chi phí tương ứng
    overhead: Decimal = _ZERO    # 154032 — chi phí sản xuất chung
    other: Decimal = _ZERO       # 154033 — chi phí khác
    labor_manual: bool = False
    overhead_manual: bool = False
    other_manual: bool = False

    @property
    def total(self) -> Decimal:
        return self.labor + self.overhead + self.other

    @property
    def manual_flags(self) -> dict[str, bool]:
        """Cờ sửa tay theo tên pool ('labor' / 'overhead' / 'other')."""
        return {
            "labor": self.labor_manual,
            "overhead": self.overhead_manual,
            "other": self.other_manual,
        }


@dataclass
class CostingInput:
    """One finished product's raw inputs (the columns the user types)."""

    code: str
    name: str = ""
    quantity: Decimal = field(default_factory=lambda: _ZERO)
    material_cost: Decimal = field(default_factory=lambda: _ZERO)  # 15401 NVL

    @property
    def is_empty(self) -> bool:
        return not self.code.strip() and not self.quantity and not self.material_cost


@dataclass
class CostingRow:
    """A product after allocation — the cost breakdown the report shows."""

    code: str
    name: str
    quantity: Decimal
    material_cost: Decimal   # 15401
    labor_cost: Decimal      # 15402 (allocated)
    overhead_cost: Decimal   # 154032 (allocated)
    other_cost: Decimal      # 154033 (allocated)

    @property
    def total_cost(self) -> Decimal:
        """Tổng giá thành = NVL + nhân công + SX chung + khác."""
        return (
            self.material_cost + self.labor_cost
            + self.overhead_cost + self.other_cost
        )

    @property
    def unit_cost(self) -> Decimal:
        """Giá thành đơn vị (154/Sp) — total ÷ quantity, 0 when no quantity."""
        if self.quantity == _ZERO:
            return _ZERO
        return (self.total_cost / self.quantity).quantize(Decimal("1"))

    def unit_of(self, component: Decimal) -> Decimal:
        """A per-unit cost component (15401/sp, 15402/sp, …)."""
        if self.quantity == _ZERO:
            return _ZERO
        return (component / self.quantity).quantize(Decimal("1"))

    # Đơn giá từng thành phần, khớp các cột "…/sp" của Bảng tính giá thành in ra.
    # Công ty gộp SXC (154032) + Khác (154033) thành một cấp đơn giá "15403/sp".
    @property
    def unit_material(self) -> Decimal:
        """15401/sp — đơn giá NVL trực tiếp."""
        return self.unit_of(self.material_cost)

    @property
    def unit_labor(self) -> Decimal:
        """15402/sp — đơn giá nhân công."""
        return self.unit_of(self.labor_cost)

    @property
    def unit_overhead_other(self) -> Decimal:
        """15403/sp — đơn giá (SX chung + chi phí khác) gộp."""
        return self.unit_of(self.overhead_cost + self.other_cost)

    @property
    def unit_components_sum(self) -> Decimal:
        """154/Sp (cột đơn giá) = tổng ba đơn giá thành phần đã làm tròn.

        Có thể lệch vài đồng so với :attr:`unit_cost` (tổng ÷ SL) do làm tròn
        từng thành phần — đúng như hai cột "154/Sp" trên tờ in.
        """
        return self.unit_material + self.unit_labor + self.unit_overhead_other


@dataclass
class CostingSheet:
    period_key: str
    pools: CostPools
    rows: list[CostingRow] = field(default_factory=list)

    @property
    def total_quantity(self) -> Decimal:
        return sum((r.quantity for r in self.rows), _ZERO)

    @property
    def total_material(self) -> Decimal:
        return sum((r.material_cost for r in self.rows), _ZERO)

    @property
    def total_labor(self) -> Decimal:
        return sum((r.labor_cost for r in self.rows), _ZERO)

    @property
    def total_overhead(self) -> Decimal:
        return sum((r.overhead_cost for r in self.rows), _ZERO)

    @property
    def total_other(self) -> Decimal:
        return sum((r.other_cost for r in self.rows), _ZERO)

    @property
    def grand_total(self) -> Decimal:
        return sum((r.total_cost for r in self.rows), _ZERO)

    @property
    def total_allocated(self) -> Decimal:
        """Tổng ba pool đã thực sự phân bổ vào các sản phẩm."""
        return self.total_labor + self.total_overhead + self.total_other

    @property
    def unallocated_pools(self) -> Decimal:
        """Phần pool KHÔNG vào được giá thành (thường do Σ NVL = 0).

        Phân bổ dựa trên tỷ lệ NVL, nên khi cả kỳ không có đồng NVL nào thì nhân
        công / SX chung / khác không có tiêu thức để chia và bị bỏ ra ngoài giá
        thành. Bảng giá thành cảnh báo số này để kế toán không mất tiền pool mà
        không hay biết.
        """
        return self.pools.total - self.total_allocated


# ----- Bảng tính NVL trực tiếp (TK 15401) — ma trận SP × loại NVL -----------
# Phần chi tiết của cột NVL (15401): mỗi thành phẩm tiêu hao bao nhiêu tiền của
# từng loại nguyên vật liệu (theo định mức × SL × đơn giá xuất bình quân).


@dataclass(frozen=True)
class MaterialCell:
    """Lượng và giá trị một loại NVL dùng cho một sản phẩm."""

    qty: Decimal = _ZERO
    value: Decimal = _ZERO


@dataclass
class MaterialMatrixRow:
    """Một sản phẩm với phần tiêu hao NVL tách theo mã NVL."""

    product_code: str
    product_name: str
    quantity: Decimal
    cells: dict[str, MaterialCell] = field(default_factory=dict)

    def value_of(self, material_code: str) -> Decimal:
        cell = self.cells.get(material_code)
        return cell.value if cell else _ZERO

    def qty_of(self, material_code: str) -> Decimal:
        cell = self.cells.get(material_code)
        return cell.qty if cell else _ZERO

    @property
    def total_value(self) -> Decimal:
        """Cột "Cộng" — tổng NVL của SP, khớp cột 15401 bên Bảng giá thành."""
        return sum((c.value for c in self.cells.values()), _ZERO)


@dataclass
class MaterialMatrix:
    period_key: str
    materials: list[str] = field(default_factory=list)          # cột, đã sắp xếp
    material_names: dict[str, str] = field(default_factory=dict)
    unit_prices: dict[str, Decimal] = field(default_factory=dict)  # ĐG xuất / NVL
    rows: list[MaterialMatrixRow] = field(default_factory=list)

    def material_qty(self, material_code: str) -> Decimal:
        return sum((r.qty_of(material_code) for r in self.rows), _ZERO)

    def material_value(self, material_code: str) -> Decimal:
        return sum((r.value_of(material_code) for r in self.rows), _ZERO)

    @property
    def grand_total(self) -> Decimal:
        return sum((r.total_value for r in self.rows), _ZERO)
