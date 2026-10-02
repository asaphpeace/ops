"""Renders the Customer Intelligence table (frontend/src/views/
CustomersView.vue) to a themed PDF — same reportlab/Platypus approach and
shared theme as weekly_report_pdf.py (see pdf_theme.py). Built specifically
so a "share this list" request doesn't have to fall back to Ctrl+P, which
prints the live dark-themed page badly.

Two columns the live table has are deliberately never offered here at all
(not just excluded by default):
  - Renewal — Customer.renewal_date is real but currently unverified data,
    confirmed elsewhere in this app's own history, so this export never
    offers a path to hand it out looking authoritative.
  - Health — an internal 0-100 support/engineering signal, not something
    with an agreed external definition; hard to justify if someone outside
    the team asks what it means. Stays visible in the live app, just not
    exportable.

Column set mirrors CustomersView.vue's real `columns` array minus those
two; the caller picks which of the rest to include and in what order —
see COLUMN_ORDER below for the full exportable set and COLUMN_LABELS for
the header text (kept in sync with the frontend's own column labels).
"""
import io

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from app.services.pdf_theme import (
    styles, p as _p, page_frame,
    GREEN, AMBER, RED, PURPLE, ACCENT, TEXT, TEXT2, TEXT3, SURFACE2, BORDER, BORDER2,
    GREEN_DIM, AMBER_DIM, RED_DIM, PURPLE_DIM, ACCENT_DIM,
)

# Every exportable column, in the same left-to-right order the live table
# uses. Renewal and Health are not in this list at all — see module docstring.
COLUMN_ORDER = [
    "name", "tier", "csm", "package", "prod_version", "infra",
    "days_since_upgrade", "upgrades", "open_cases", "migration",
]
COLUMN_LABELS = {
    "name": "Customer", "tier": "Tier", "csm": "CSM",
    "package": "Package", "prod_version": "Prod Version", "infra": "Infra",
    "days_since_upgrade": "Days Since Upgrade", "upgrades": "Upgrades",
    "open_cases": "Open Cases", "migration": "Migration",
}
# Relative width weights (cm) at the live table's own proportions — narrow
# badge columns stay narrow, Customer gets the most room. Scaled to fill
# the page in render_pdf() based on which columns are actually selected.
_COLUMN_WEIGHTS = {
    "name": 4.6, "tier": 1.9, "csm": 2.0, "package": 2.2,
    "prod_version": 2.4, "infra": 1.7, "days_since_upgrade": 2.6,
    "upgrades": 1.8, "open_cases": 1.8, "migration": 2.2,
}

_TIER_COLORS = {"Premier": (AMBER_DIM, AMBER), "Strategic": (PURPLE_DIM, PURPLE), "Scale": (ACCENT_DIM, ACCENT)}
_INFRA_COLORS = {"Old": (RED_DIM, RED), "New": (GREEN_DIM, GREEN), "Mixed": (AMBER_DIM, AMBER)}


def _badge(ss, text: str, bg, fg, width: float) -> Table:
    t = Table([[_p(text, ParagraphStyle("Badge", fontName="PlexSans-SemiBold", fontSize=7, textColor=fg))]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("ROUNDEDCORNERS", [3, 3, 3, 3]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _colored(ss, text, hex_color) -> Paragraph:
    return Paragraph(f'<font color="{hex_color}">{text}</font>', ss["TableCell"])


def _hex(c) -> str:
    return "#%02x%02x%02x" % (round(c.red * 255), round(c.green * 255), round(c.blue * 255))


def _is_jvm_version(version: str | None) -> bool:
    """Every real web-app release is 8.x+ (confirmed throughout this app —
    the version thresholds just below are themselves 8.23/8.27). A version
    with a major number below 8 (6.46.21, 5.48.2, ...) is real JVM desktop-
    client numbering, not a web version — confirmed live: several
    customers carry a real 6.x.x version with jvm_client never flagged
    true. Checked independently of the jvm_client column so the export
    stays correct even when that flag is stale or wrong."""
    if not version:
        return False
    try:
        major = int(version.split(".")[0].replace("-R", ""))
    except ValueError:
        return False
    return major < 8


def _version_cell(ss, row: dict, width: float):
    # JVM clients are still on the old desktop client, not the web app —
    # comparing their prod_version (blank for most real JVM customers, and
    # not a meaningful "is this outdated" signal even on the ones that have
    # one) against the same red/amber web-version thresholds is confusing
    # at best. A JVM badge here — replacing the version text, not
    # alongside it — is the honest answer and also frees the Customer
    # column from carrying this badge instead.
    version = row.get("prod_version")
    if row.get("jvm_client") or _is_jvm_version(version):
        return _badge(ss, "JVM", PURPLE_DIM, PURPLE, width)
    if not version:
        return _p("—", ss["TableCellMuted"])
    try:
        num = float(version.replace("-R", ""))
    except ValueError:
        num = None
    if num is not None and num < 8.23:
        return _colored(ss, version, _hex(RED))
    if num is not None and num < 8.27:
        return _colored(ss, version, _hex(AMBER))
    return _p(version, ss["TableCell"])


def _days_since_cell(ss, days: int | None):
    if days is None:
        return _p("Never", ss["TableCellMuted"])
    color = RED if days > 365 else AMBER if days > 90 else GREEN
    return _colored(ss, f"{days}d", _hex(color))


def _upgrades_cell(ss, used: int, limit: int):
    color = RED if limit and used >= limit else AMBER if limit and used > limit * 0.7 else TEXT3
    return _colored(ss, f"{used}/{limit}", _hex(color))


def _migration_cell(ss, stage: str | None):
    if not stage:
        return _p("—", ss["TableCellMuted"])
    color = GREEN if stage == "Complete" else ACCENT if stage == "In Progress" else TEXT3
    return _colored(ss, stage, _hex(color))


def _render_cell(ss, key: str, row: dict, width: float):
    if key == "name":
        return _p(row["name"], ss["TableCell"])
    if key == "tier":
        bg, fg = _TIER_COLORS.get(row["tier"], (SURFACE2, TEXT3))
        return _badge(ss, row["tier"] or "—", bg, fg, width)
    if key == "csm":
        return _p(row.get("csm") or "—", ss["TableCell"])
    if key == "package":
        return _p(row.get("package") or "—", ss["TableCell"])
    if key == "prod_version":
        return _version_cell(ss, row, width)
    if key == "infra":
        bg, fg = _INFRA_COLORS.get(row["infra"], (SURFACE2, TEXT3))
        return _badge(ss, row["infra"] or "—", bg, fg, width)
    if key == "days_since_upgrade":
        return _days_since_cell(ss, row.get("days_since_upgrade"))
    if key == "upgrades":
        return _upgrades_cell(ss, row.get("upgrades_used") or 0, row.get("upgrades_limit") or 0)
    if key == "open_cases":
        oc = row.get("open_cases")
        return _p(oc if oc is not None else "—", ss["TableCell"])
    if key == "migration":
        return _migration_cell(ss, row.get("migration_stage"))
    return _p("—", ss["TableCellMuted"])


def render_pdf(customers: list[dict], columns: list[str], generated_at: str) -> bytes:
    """`customers` is a list of already-resolved row dicts (see
    routers/customers.py's export endpoint for exactly what it assembles per
    column); `columns` is the caller's chosen subset of COLUMN_ORDER, in
    display order. Landscape A4 — this table is wide."""
    cols = [c for c in COLUMN_ORDER if c in columns]  # keep canonical order regardless of request order
    buf = io.BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buf, pagesize=page_size,
        topMargin=1.4 * cm, bottomMargin=1.4 * cm, leftMargin=1.2 * cm, rightMargin=1.2 * cm,
        title="Sedna Ops — Customer Version List",
    )
    ss = styles()
    story = []

    story.append(Paragraph("Sedna Ops", ss["Eyebrow"]))
    story.append(Paragraph("Customer Version List", ss["ReportTitle"]))
    story.append(Paragraph(f"{len(customers)} customers &nbsp;·&nbsp; generated {generated_at}", ss["ReportSub"]))
    story.append(Spacer(1, 10))

    full_w = page_size[0] - 2.4 * cm
    total_weight = sum(_COLUMN_WEIGHTS.get(c, 2.0) for c in cols)
    col_widths = [full_w * (_COLUMN_WEIGHTS.get(c, 2.0) / total_weight) for c in cols]

    header = [COLUMN_LABELS[c] for c in cols]
    rows = [[_render_cell(ss, c, row, w) for c, w in zip(cols, col_widths)] for row in customers]

    head_row = [_p(h, ss["TableHead"]) for h in header]
    data = [head_row] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SURFACE2),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, BORDER2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, BORDER),
    ]))
    story.append(t)

    doc.build(story, onFirstPage=page_frame("Sedna Ops — Customer Version List"), onLaterPages=page_frame("Sedna Ops — Customer Version List"))
    return buf.getvalue()
