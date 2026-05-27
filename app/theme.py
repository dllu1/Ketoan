"""Theme loader: dark palette + QSS + JetBrains Mono font."""
from __future__ import annotations

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from app.config import FONTS_DIR, QSS_DIR


def apply_theme(app: QApplication) -> None:
    _load_fonts()
    qss_file = QSS_DIR / "dark.qss"
    if qss_file.exists():
        app.setStyleSheet(qss_file.read_text(encoding="utf-8"))


def _load_fonts() -> None:
    if not FONTS_DIR.exists():
        return
    for ttf in FONTS_DIR.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(ttf))
    for otf in FONTS_DIR.glob("*.otf"):
        QFontDatabase.addApplicationFont(str(otf))
