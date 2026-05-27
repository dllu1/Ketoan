"""Application-wide constants and paths."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Hung Phat Accounting"
ORG_NAME = "Hung Phat M&E"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESOURCES_DIR = PROJECT_ROOT / "ui" / "resources"
QSS_DIR = RESOURCES_DIR / "qss"
FONTS_DIR = RESOURCES_DIR / "fonts"
ICONS_DIR = RESOURCES_DIR / "icons"

_appdata = os.environ.get("APPDATA") or str(PROJECT_ROOT)
USER_DATA_DIR = Path(_appdata) / "HungPhatAccounting"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = USER_DATA_DIR / "ketoan.db"

ACCENT = "#3b82f6"
BG_BASE = "#0b1018"
BG_PANEL = "#111827"
BG_ELEVATED = "#1f2937"
TEXT_PRIMARY = "#e5e7eb"
TEXT_MUTED = "#9ca3af"
BORDER = "#1f2a3a"
