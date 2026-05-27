"""Design tokens — mirror components/styles.css exactly.

Lines and hovers are intentionally brand-tinted translucent overlays
rendered as solid hex equivalents (Qt's QSS does not understand color-mix
or oklch). Values below are pre-mixed against the bg #0b1018.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Literal


class Density(str, Enum):
    COMPACT = "compact"
    COZY = "cozy"
    COMFY = "comfy"


class Layout(str, Enum):
    A = "A"
    B = "B"
    C = "C"


FontFamily = Literal[
    "JetBrains Mono",
    "IBM Plex Mono",
    "Inter",
    "Segoe UI",
]


@dataclass(frozen=True)
class Tokens:
    # ----- brand & status ---------------------------------------------------
    brand: str = "#a1caff"
    brand_300: str = "#cfe2ff"
    brand_400: str = "#b5d4ff"
    brand_500: str = "#a1caff"
    brand_600: str = "#7fb0ec"
    brand_700: str = "#5e95d6"
    brand_800: str = "#3c6fa9"
    brand_900: str = "#264a7a"
    brand_tint: str = "#1a2538"
    brand_tint_strong: str = "#22324a"
    brand_pressed: str = "#0a1220"  # dark text used on brand-filled buttons

    good: str = "#7ed3a3"
    warn: str = "#e8c069"
    bad: str = "#e8927a"

    # ----- surfaces ---------------------------------------------------------
    bg: str = "#0b1018"
    panel: str = "#121925"
    panel_solid: str = "#121925"
    card: str = "#161e2c"
    card_2: str = "#1a2333"
    elevated: str = "#1f2937"

    # ----- text -------------------------------------------------------------
    txt: str = "#e6edf3"
    txt_2: str = "#b6c2d2"
    txt_3: str = "#7e8da3"
    txt_4: str = "#5b6a82"

    # ----- borders (pre-mixed against bg) ----------------------------------
    line: str = "#1c2538"          # ~ rgba(161,202,255,0.10)
    line_strong: str = "#2a3953"   # ~ rgba(161,202,255,0.18)
    line_soft: str = "#171f2d"     # ~ rgba(161,202,255,0.06)
    hover: str = "#171f2d"         # ~ rgba(161,202,255,0.06)
    active: str = "#22324a"        # ~ rgba(161,202,255,0.14)

    # ----- typography -------------------------------------------------------
    font_family: FontFamily = "JetBrains Mono"
    font_size: int = 13
    font_size_small: int = 11
    font_size_label: int = 10

    # ----- layout -----------------------------------------------------------
    radius: int = 8
    pad: int = 16
    row_h: int = 30
    kpi_pad: int = 18
    border_strength: int = 1
    density: Density = Density.COZY
    layout: Layout = Layout.A

    def with_(self, **overrides) -> "Tokens":
        return replace(self, **overrides)


_active: Tokens = Tokens()


def active_tokens() -> Tokens:
    return _active


def set_active_tokens(tokens: Tokens) -> None:
    global _active
    _active = tokens


_DENSITY_PRESETS: dict[Density, dict[str, int]] = {
    Density.COMPACT: {"font_size": 12, "pad": 12, "row_h": 26, "kpi_pad": 14},
    Density.COZY:    {"font_size": 13, "pad": 16, "row_h": 30, "kpi_pad": 18},
    Density.COMFY:   {"font_size": 14, "pad": 20, "row_h": 36, "kpi_pad": 22},
}


def tokens_for_density(base: Tokens, density: Density) -> Tokens:
    return base.with_(density=density, **_DENSITY_PRESETS[density])
