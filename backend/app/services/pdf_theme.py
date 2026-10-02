"""Shared reportlab theme for every PDF this app generates — colors, fonts,
and the small set of Platypus building blocks (tile/table/card) styled to
match the live app. Split out of weekly_report_pdf.py (the first PDF built
this way) so a second report (customer_export_pdf.py) doesn't duplicate
~120 lines of theme code, and so the two can never visually drift apart.

Visual language is pulled from the live app, not invented here — colors
are the exact hex values from frontend/src/assets/main.css's `:root`
design tokens (that file's own header calls them "locked, do not change
without explicit sign-off", so this reads them rather than re-guessing
them), and the type family is IBM Plex Sans (OFL-licensed, bundled under
app/assets/fonts/) chosen as an open-license visual match for the app's
Inter/Segoe UI system-font stack — reportlab can't load a proprietary
system font from inside the Linux container, so this is the closest
freely-redistributable substitute rather than a generic Helvetica
fallback.
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Table, TableStyle

# ── Design tokens, copied 1:1 from frontend/src/assets/main.css :root ──────
BG          = colors.HexColor("#080d17")
SURFACE     = colors.HexColor("#0f1623")
SURFACE2    = colors.HexColor("#162035")
SURFACE3    = colors.HexColor("#1c2a45")
BORDER      = colors.HexColor("#1a2640")
BORDER2     = colors.HexColor("#243350")
TEXT        = colors.HexColor("#dde5f4")
TEXT2       = colors.HexColor("#7d9abf")
TEXT3       = colors.HexColor("#3d5475")
ACCENT      = colors.HexColor("#3b7ff5")
GREEN       = colors.HexColor("#0fba81")
AMBER       = colors.HexColor("#f0a030")
RED         = colors.HexColor("#e8445a")
PURPLE      = colors.HexColor("#9b6cf5")
TEAL        = colors.HexColor("#0bc5ea")

# "-dim" tokens are `rgba(color, 0.1)` over the app's dark surface — approximated
# here as a low-alpha fill of the same hue so a tinted table/tile background
# reads the same way against this doc's own dark page background.
GREEN_DIM  = colors.Color(15 / 255, 186 / 255, 129 / 255, alpha=0.16)
AMBER_DIM  = colors.Color(240 / 255, 160 / 255, 48 / 255, alpha=0.16)
RED_DIM    = colors.Color(232 / 255, 68 / 255, 90 / 255, alpha=0.16)
ACCENT_DIM = colors.Color(59 / 255, 127 / 255, 245 / 255, alpha=0.16)
PURPLE_DIM = colors.Color(155 / 255, 108 / 255, 245 / 255, alpha=0.16)

RAG_BG   = {"Red": RED_DIM, "Amber": AMBER_DIM, "Green": GREEN_DIM}
RAG_TEXT = {"Red": RED, "Amber": AMBER, "Green": GREEN}

_FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
_FONTS_REGISTERED = False


def register_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont("PlexSans", os.path.join(_FONT_DIR, "IBMPlexSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("PlexSans-Medium", os.path.join(_FONT_DIR, "IBMPlexSans-Medium.ttf")))
    pdfmetrics.registerFont(TTFont("PlexSans-SemiBold", os.path.join(_FONT_DIR, "IBMPlexSans-SemiBold.ttf")))
    pdfmetrics.registerFont(TTFont("PlexSans-Bold", os.path.join(_FONT_DIR, "IBMPlexSans-Bold.ttf")))
    _FONTS_REGISTERED = True


def styles():
    register_fonts()
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("ReportTitle", fontName="PlexSans-Bold", fontSize=22, leading=26, textColor=TEXT, spaceAfter=2))
    ss.add(ParagraphStyle("ReportSub", fontName="PlexSans", fontSize=10, leading=13, textColor=TEXT2, spaceAfter=4))
    # Matches .md-eyebrow / .puq-head: small, bold, uppercase, muted.
    ss.add(ParagraphStyle("Eyebrow", fontName="PlexSans-Bold", fontSize=8, leading=10, textColor=TEXT3, spaceAfter=2))
    ss.add(ParagraphStyle("SectionHeading", fontName="PlexSans-Bold", fontSize=15, leading=18, textColor=ACCENT, spaceBefore=0, spaceAfter=3))
    ss.add(ParagraphStyle("SectionSub", fontName="PlexSans", fontSize=9, leading=12, textColor=TEXT3, spaceAfter=10))
    ss.add(ParagraphStyle("SubHeading", fontName="PlexSans-SemiBold", fontSize=10.5, leading=13, textColor=TEXT, spaceBefore=12, spaceAfter=6))
    ss.add(ParagraphStyle("Bluf", fontName="PlexSans", fontSize=11, leading=16, textColor=TEXT, spaceAfter=10))
    ss.add(ParagraphStyle("Body", fontName="PlexSans", fontSize=8.5, leading=12, textColor=TEXT))
    ss.add(ParagraphStyle("BodyMuted", fontName="PlexSans", fontSize=8.5, leading=12, textColor=TEXT2))
    ss.add(ParagraphStyle("Small", fontName="PlexSans", fontSize=8.5, leading=12, textColor=TEXT3))
    ss.add(ParagraphStyle("KpiValue", fontName="PlexSans-Bold", fontSize=15, leading=18, textColor=TEXT, alignment=TA_CENTER))
    ss.add(ParagraphStyle("KpiLabel", fontName="PlexSans-Medium", fontSize=6.3, leading=8, textColor=TEXT3, alignment=TA_CENTER))
    ss.add(ParagraphStyle("RagArea", fontName="PlexSans-Bold", fontSize=7.5, leading=9, textColor=TEXT3, alignment=TA_CENTER))
    ss.add(ParagraphStyle("TableHead", fontName="PlexSans-SemiBold", fontSize=7.5, leading=9, textColor=TEXT2))
    ss.add(ParagraphStyle("TableCell", fontName="PlexSans", fontSize=8, leading=10.5, textColor=TEXT))
    ss.add(ParagraphStyle("TableCellMuted", fontName="PlexSans", fontSize=8, leading=10.5, textColor=TEXT3))
    return ss


def p(text, style) -> Paragraph:
    return Paragraph("" if text is None else str(text), style)


def table(ss, header: list[str], rows: list[list], col_widths=None) -> Table:
    head = [p(h, ss["TableHead"]) for h in header]
    body = [[cell if isinstance(cell, Paragraph) else p(cell, ss["TableCell"]) for cell in row] for row in rows]
    data = [head] + body
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), SURFACE2),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, BORDER2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, BORDER),
    ]
    t.setStyle(TableStyle(style))
    return t


def empty(ss, text: str = "None.") -> Paragraph:
    return Paragraph(text, ss["Small"])


def card_wrap(ss, flowables: list, pad: float = 8, width: float = 18 * cm) -> Table:
    """Wraps a block of flowables in a single-cell rounded card matching
    the app's `.tw` panel (SURFACE background, BORDER outline, radius)."""
    inner = Table([[flowables]], colWidths=[width])
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
    ]))
    return inner


def page_frame(footer_label: str):
    """Returns a canvas callback for SimpleDocTemplate's onFirstPage/
    onLaterPages — full-page dark background + a quiet footer, since the
    app never renders on a white page and neither should its exports."""
    def _draw(canvas, doc) -> None:
        # doc.pagesize is the real page size in use (e.g. landscape(A4) is
        # wider than plain A4) — a hardcoded A4 here left a white strip on
        # the right of any landscape export.
        page_w, page_h = doc.pagesize
        canvas.saveState()
        canvas.setFillColor(BG)
        canvas.rect(0, 0, page_w, page_h, fill=1, stroke=0)
        canvas.setFont("PlexSans", 7)
        canvas.setFillColor(TEXT3)
        canvas.drawString(1.5 * cm, 0.9 * cm, footer_label)
        canvas.drawRightString(page_w - 1.5 * cm, 0.9 * cm, f"Page {doc.page}")
        canvas.restoreState()
    return _draw
