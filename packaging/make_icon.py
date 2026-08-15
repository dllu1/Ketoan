"""Generate the Windows application icon (packaging/HungPhat.ico).

Run once — the .ico is committed so building doesn't require Pillow. Re-run only
if the brand colours in ``ui/tokens.py`` change.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "HungPhat.ico"
BRAND = (47, 111, 237)      # tokens LIGHT.brand  #2f6fed
BRAND_DARK = (27, 74, 160)  # tokens LIGHT.brand_800
WHITE = (255, 255, 255)

_FONT_DIR = Path(__file__).resolve().parents[1] / "ui" / "resources" / "fonts"


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONT_DIR / "JetBrainsMono-Bold.ttf"), size)


def _render(size: int) -> Image.Image:
    # Draw at 4x then downsample: cheap anti-aliasing for the rounded corners.
    scale = 4
    px = size * scale
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    radius = int(px * 0.22)
    draw.rounded_rectangle([0, 0, px - 1, px - 1], radius=radius, fill=BRAND)
    # Subtle bottom band so the mark reads as a ledger card, not a flat square.
    draw.rounded_rectangle(
        [0, int(px * 0.70), px - 1, px - 1], radius=radius, fill=BRAND_DARK
    )
    draw.rectangle([0, int(px * 0.70), px - 1, int(px * 0.80)], fill=BRAND_DARK)

    text = "HP"
    font = _font(int(px * 0.42))
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(
        (
            (px - (box[2] - box[0])) / 2 - box[0],
            px * 0.34 - (box[3] - box[1]) / 2 - box[1],
        ),
        text,
        font=font,
        fill=WHITE,
    )
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [_render(s) for s in sizes]
    images[-1].save(OUT, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
