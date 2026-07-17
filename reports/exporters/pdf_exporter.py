"""Render a :class:`ReportDocument` to a PDF via reportlab (platypus)."""
from __future__ import annotations

from pathlib import Path

from app.config import FONTS_DIR
from reports.report_tables import ReportDocument, ReportTable, format_cell

_HEADER_BG = "#1f2937"
_TOTAL_BG = "#eff3f8"
_GRID = "#c8d0dc"

# The built-in PDF fonts (Helvetica…) have no Vietnamese glyphs, so accented
# characters render as tofu boxes. Register a Unicode TTF instead — prefer a
# proportional system font, fall back to the JetBrains Mono bundled with the
# app (always present, full Vietnamese coverage).
_WIN_FONTS = Path("C:/Windows/Fonts")
_FONT_CANDIDATES = [
    (_WIN_FONTS / "tahoma.ttf", _WIN_FONTS / "tahomabd.ttf"),
    (_WIN_FONTS / "arial.ttf", _WIN_FONTS / "arialbd.ttf"),
    (_WIN_FONTS / "segoeui.ttf", _WIN_FONTS / "segoeuib.ttf"),
    (FONTS_DIR / "JetBrainsMono-Regular.ttf", FONTS_DIR / "JetBrainsMono-Bold.ttf"),
]

_REGULAR = "ReportFont"
_BOLD = "ReportFont-Bold"
_fonts_ready = False


def _register_fonts() -> tuple[str, str]:
    """Register a Vietnamese-capable font once; return (regular, bold) names.

    Falls back to Helvetica only if no candidate TTF is found (Latin text still
    prints, accents may not — but the bundled font guarantees they will).
    """
    global _fonts_ready
    if _fonts_ready:
        return _REGULAR, _BOLD

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for regular_path, bold_path in _FONT_CANDIDATES:
        if not regular_path.exists():
            continue
        bold = bold_path if bold_path.exists() else regular_path
        try:
            pdfmetrics.registerFont(TTFont(_REGULAR, str(regular_path)))
            pdfmetrics.registerFont(TTFont(_BOLD, str(bold)))
        except Exception:  # noqa: BLE001 — try the next candidate
            continue
        pdfmetrics.registerFontFamily(_REGULAR, normal=_REGULAR, bold=_BOLD)
        _fonts_ready = True
        return _REGULAR, _BOLD

    return "Helvetica", "Helvetica-Bold"


def export_pdf(doc: ReportDocument, path: str | Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    regular, bold = _register_fonts()

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "RptTitle", parent=styles["Title"], fontName=bold, fontSize=15, spaceAfter=2,
    )
    sub_style = ParagraphStyle(
        "RptSub", parent=styles["Normal"], fontName=regular, fontSize=9, alignment=1,
        textColor=colors.HexColor("#55607a"), spaceAfter=10,
    )
    cap_style = ParagraphStyle(
        "RptCap", parent=styles["Normal"], fontName=bold, fontSize=10, spaceBefore=6,
        spaceAfter=2, leading=12, textColor=colors.HexColor("#1f2937"),
    )

    path = Path(path)
    pdf = SimpleDocTemplate(
        str(path),
        pagesize=landscape(A4),
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=doc.title,
    )

    flow = [Paragraph(doc.title, title_style), Paragraph(doc.subtitle, sub_style)]
    for table in doc.tables:
        if table.caption:
            flow.append(Paragraph(f"<b>{table.caption}</b>", cap_style))
        flow.append(_make_table(table, colors, Table, TableStyle, regular, bold))
        flow.append(Spacer(1, 6 * mm))
    pdf.build(flow)
    return path


def _make_table(table: ReportTable, colors, Table, TableStyle, regular, bold):
    header = [c.header for c in table.columns]
    data = [header]
    for row in table.rows:
        data.append([format_cell(cell) for cell in row])
    total_idx = None
    if table.total_row is not None:
        total_idx = len(data)
        data.append([format_cell(cell) for cell in table.total_row])

    tbl = Table(data, repeatRows=1, hAlign="LEFT")
    style = [
        ("FONTNAME", (0, 0), (-1, -1), regular),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("FONTNAME", (0, 0), (-1, 0), bold),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_HEADER_BG)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(_GRID)),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for c, column in enumerate(table.columns):
        if column.numeric:
            style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    if total_idx is not None:
        style.append(("FONTNAME", (0, total_idx), (-1, total_idx), bold))
        style.append(
            ("BACKGROUND", (0, total_idx), (-1, total_idx), colors.HexColor(_TOTAL_BG))
        )
    tbl.setStyle(TableStyle(style))
    return tbl
