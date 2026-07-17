"""Tests for the product-costing worksheet (Bảng tính giá thành sản phẩm).

Verifies the blue-note allocation rule: non-material pools split by NVL ratio,
total = NVL + pools, unit = total / quantity — plus exact-sum rounding and
persistence.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.models.costing import CostingInput, CostPools
from domain.services.costing_service import CostingService


def _inp(code, qty, nvl, name="") -> CostingInput:
    return CostingInput(
        code=code, name=name or code,
        quantity=Decimal(str(qty)), material_cost=Decimal(str(nvl)),
    )


@pytest.fixture
def in_memory_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    monkeypatch.setattr("app.config.DB_PATH", db_file)
    monkeypatch.setattr("data.database.DB_PATH", db_file)

    import data.database as db_mod
    db_mod._conn = None
    db_mod.init_database()
    yield db_mod.get_connection()
    db_mod.close_connection()


# ----- allocation by NVL ratio --------------------------------------------


def test_pools_split_in_proportion_to_nvl():
    svc = CostingService()
    inputs = [_inp("P1", qty=100, nvl=600), _inp("P2", qty=50, nvl=400)]
    pools = CostPools(labor=Decimal("1000"))  # total NVL = 1000 → ratios .6/.4
    sheet = svc.compute(inputs, pools)

    p1, p2 = sheet.rows
    assert p1.labor_cost == Decimal("600")
    assert p2.labor_cost == Decimal("400")
    # Total cost = NVL + allocated pools.
    assert p1.total_cost == Decimal("1200")   # 600 + 600
    assert p2.total_cost == Decimal("800")    # 400 + 400
    # Unit cost = total / quantity.
    assert p1.unit_cost == Decimal("12")
    assert p2.unit_cost == Decimal("16")


def test_all_pools_allocated_and_summed():
    svc = CostingService()
    inputs = [_inp("P1", 10, 700), _inp("P2", 10, 300)]
    pools = CostPools(labor=Decimal("100"), overhead=Decimal("50"), other=Decimal("10"))
    sheet = svc.compute(inputs, pools)

    assert sheet.total_labor == Decimal("100")
    assert sheet.total_overhead == Decimal("50")
    assert sheet.total_other == Decimal("10")
    # Grand total = sum NVL + all pools.
    assert sheet.grand_total == Decimal("1160")  # 1000 + 160


def test_rounding_residual_keeps_column_total_exact():
    svc = CostingService()
    # Three equal shares of 10 → 3.33 each; residual must keep the sum at 10.
    inputs = [_inp("A", 1, 1), _inp("B", 1, 1), _inp("C", 1, 1)]
    pools = CostPools(labor=Decimal("10"))
    sheet = svc.compute(inputs, pools)
    assert sum(r.labor_cost for r in sheet.rows) == Decimal("10")


def test_zero_total_nvl_allocates_nothing():
    svc = CostingService()
    inputs = [_inp("P1", 10, 0), _inp("P2", 10, 0)]
    pools = CostPools(labor=Decimal("500"))
    sheet = svc.compute(inputs, pools)
    assert all(r.labor_cost == Decimal("0") for r in sheet.rows)


def test_unit_cost_zero_when_no_quantity():
    svc = CostingService()
    sheet = svc.compute([_inp("P1", 0, 1000)], CostPools(labor=Decimal("0")))
    assert sheet.rows[0].unit_cost == Decimal("0")


# ----- persistence ---------------------------------------------------------


def test_save_then_load_recomputes(in_memory_db):
    from data.repositories.costing_repo import CostingRepository

    svc = CostingService(CostingRepository(in_memory_db))
    inputs = [_inp("Aty24", 44_800, 600), _inp("Aty35", 10_100, 400)]
    pools = CostPools(labor=Decimal("1000"))
    svc.save("2025", inputs, pools)

    sheet = svc.load("2025")
    assert len(sheet.rows) == 2
    assert sheet.pools.labor == Decimal("1000")
    assert sheet.rows[0].labor_cost == Decimal("600")
    assert sheet.total_labor == Decimal("1000")
