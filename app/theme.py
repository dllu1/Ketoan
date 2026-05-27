"""Theme loader: registers fonts, sets app-wide QFont, applies QSS template."""
from __future__ import annotations

from dataclasses import asdict
from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from app.config import FONTS_DIR, QSS_DIR
from ui.tokens import Tokens, active_tokens, set_active_tokens

_QSS_FILES: tuple[str, ...] = ("_base.qss", "chrome.qss", "primitives.qss")

_loaded_family: str | None = None


def apply_theme(app: QApplication, tokens: Tokens | None = None) -> None:
    """Load bundled fonts, set the active tokens, and apply rendered QSS."""
    global _loaded_family
    _loaded_family = _load_fonts()
    if tokens is None:
        tokens = active_tokens()

    # Force the loaded family name into the tokens so QSS templates and
    # QPainter both reference the same font that QFontDatabase registered.
    if _loaded_family:
        tokens = tokens.with_(font_family=_loaded_family)
    set_active_tokens(tokens)

    _apply_app_font(app, tokens)
    app.setStyleSheet(_render_qss(tokens))


def _apply_app_font(app: QApplication, tokens: Tokens) -> None:
    font = QFont(tokens.font_family, tokens.font_size)
    font.setStyleStrategy(QFont.PreferAntialias)
    font.setHintingPreference(QFont.PreferFullHinting)
    font.setKerning(True)
    # OpenType tabular numerals: optional, swallow any binding mismatch
    try:
        tag = QFont.Tag.fromString("tnum")
        font.setFeature(tag, 1)
    except Exception:
        pass
    app.setFont(font)


def _render_qss(tokens: Tokens) -> str:
    context = _token_format_map(tokens)
    parts: list[str] = []
    for name in _QSS_FILES:
        path = QSS_DIR / name
        if not path.exists():
            continue
        parts.append(path.read_text(encoding="utf-8").format(**context))
    return "\n\n".join(parts)


def _token_format_map(tokens: Tokens) -> dict[str, object]:
    raw = asdict(tokens)
    out: dict[str, object] = {}
    for key, value in raw.items():
        out[key] = value.value if isinstance(value, Enum) else value
    return out


def _load_fonts() -> str | None:
    """Register bundled fonts and return the canonical loaded family name."""
    if not FONTS_DIR.exists():
        return None
    family_name: str | None = None
    for pattern in ("*.ttf", "*.otf"):
        for font_path in FONTS_DIR.glob(pattern):
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id < 0:
                continue
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families and family_name is None:
                family_name = families[0]
    return family_name
