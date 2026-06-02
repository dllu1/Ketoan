"""Chart-of-accounts templates per circular (chế độ kế toán).

Each ``<circular>.json`` file ships one circular's official chart of accounts.
Adding support for a future circular = drop in one more JSON file here.
"""
from __future__ import annotations

import json
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def available_circulars() -> list[tuple[str, str]]:
    """Return ``[(code, label)]`` for every bundled circular template."""
    result: list[tuple[str, str]] = []
    for path in sorted(_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        result.append((data["circular"], data.get("label", data["circular"])))
    return result


def load_accounts(circular: str) -> list[dict]:
    """Return the raw account dicts (``code``/``name``/``kind``) for a circular."""
    path = _DIR / f"{circular.lower()}.json"
    if not path.exists():
        raise ValueError(f"Không có mẫu danh mục tài khoản cho '{circular}'.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["accounts"]
