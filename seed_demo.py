"""Convenience entry point to seed demo data.

    python seed_demo.py            # seed only if the database is empty
    python seed_demo.py --reset    # wipe transactional data and reseed
"""
from __future__ import annotations

import sys

from data.seed import seed_demo


def main() -> int:
    # Windows consoles default to cp1252; force UTF-8 so Vietnamese prints.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    reset = "--reset" in sys.argv
    did = seed_demo(reset=reset)
    if did:
        print("[OK] Da tao du lieu mau. Khoi dong ung dung: python main.py")
    else:
        print("[--] Da co du lieu - dung 'python seed_demo.py --reset' de tao lai.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
