"""Seed only the production-costing worksheets.

Populates "Bảng kê N–X–T nguyên vật liệu chính" and "Bảng tính giá thành sản
phẩm" for the whole-year period (2026) and the current month (2026-06) so the
Kho hàng tabs open with live numbers. Idempotent and non-destructive — it only
rewrites the worksheet tables, leaving the rest of the demo data untouched, so
it is safe to run on a database that is already seeded::

    python seed_worksheets.py
"""
from __future__ import annotations

import sys

from data.seed import seed_worksheets


def main() -> int:
    # Windows consoles default to cp1252; force UTF-8 so Vietnamese prints.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    seed_worksheets()
    print("[OK] Da tao du lieu mau cho Bang ke NVL chinh va Bang gia thanh.")
    print("     Mo tab Kho hang -> Bang ke NVL / Gia thanh de thu (ky 2026).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
