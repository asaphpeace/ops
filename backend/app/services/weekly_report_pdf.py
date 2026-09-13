"""Renders a stored WeeklyReport.snapshot to a real, multi-page PDF —
Platypus (SimpleDocTemplate + Paragraph/Table/PageBreak), the standard
reportlab approach for a structured, paginated document (per the bundled
pdf skill's own guidance), not raw canvas drawing. One page break per
major section so it prints/projects cleanly in the real weekly DevOps
priority meeting this report is built for.

Visual language is deliberately pulled from the live app, not invented
here — colors are the exact hex values from frontend/src/assets/main.css's
`:root` design tokens (that file's own header calls them "locked, do not
change without explicit sign-off", so this reads them rather than
re-guessing them), and the type family is IBM Plex Sans (OFL-licensed,
bundled under app/assets/fonts/) chosen as an open-license visual match
for the app's Inter/Segoe UI system-font stack — reportlab can't load a
proprietary system font from inside the Linux container, so this is the
closest freely-redistributable substitute rather than a generic Helvetica
fallback.
"""
import io
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
)

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
GREEN_DIM = colors.Color(15 / 255, 186 / 255, 129 / 255, alpha=0.16)
AMBER_DIM = colors.Color(240 / 255, 160 / 255, 48 / 255, alpha=0.16)
RED_DIM   = colors.Color(232 / 255, 68 / 255, 90 / 255, alpha=0.16)

_RAG_BG   = {"Red": RED_DIM, "Amber": AMBER_DIM, "Green": GREEN_DIM}
_RAG_TEXT = {"Red": RED, "Amber": AMBER, "Green": GREEN}

_FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
_FONTS_REGISTERED = False


def _register_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont("PlexSans", os.path.join(_FONT_DIR, "IBMPlexSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("PlexSans-Medium", os.path.join(_FONT_DIR, "IBMPlexSans-Medium.ttf")))
    pdfmetrics.registerFont(TTFont("PlexSans-SemiBold", os.path.join(_FONT_DIR, "IBMPlexSans-SemiBold.ttf")))
    pdfmetrics.registerFont(TTFont("PlexSans-Bold", os.path.join(_FONT_DIR, "IBMPlexSans-Bold.ttf")))
    _FONTS_REGISTERED = True


def _styles():
    _register_fonts()
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


def _p(text, style) -> Paragraph:
    return Paragraph("" if text is None else str(text), style)


def _section_header(ss, title: str, subtitle: str | None = None) -> list:
    out = [Paragraph(title, ss["SectionHeading"])]
    if subtitle:
        out.append(Paragraph(subtitle, ss["SectionSub"]))
    return out


def _kpi_tile(ss, value, label: str, width: float, accent=None) -> Table:
    value_style = ss["KpiValue"]
    if accent is not None:
        value_style = ParagraphStyle("KpiValueAccent", parent=ss["KpiValue"], textColor=accent)
    t = Table(
        [[_p(value if value is not None else "—", value_style)], [_p(label.upper(), ss["KpiLabel"])]],
        colWidths=[width],
    )
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SURFACE2),
        ("ROUNDEDCORNERS", [5, 5, 5, 5]),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER2),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("TOPPADDING", (0, 1), (-1, 1), 1),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _kpi_row(tiles: list[Table], gap: float = 0.2 * cm) -> Table:
    row = Table([tiles], colWidths=None)
    style = [
        ("LEFTPADDING", (0, 0), (-1, -1), gap / 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), gap / 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.transparent),
    ]
    row.setStyle(TableStyle(style))
    return row


def _table(ss, header: list[str], rows: list[list], col_widths=None) -> Table:
    head = [_p(h, ss["TableHead"]) for h in header]
    body = [[cell if isinstance(cell, Paragraph) else _p(cell, ss["TableCell"]) for cell in row] for row in rows]
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


def _empty(ss, text: str = "None.") -> Paragraph:
    return Paragraph(text, ss["Small"])


def _card_wrap(ss, flowables: list, pad: float = 8) -> Table:
    """Wraps a block of flowables in a single-cell rounded card matching
    the app's `.tw` panel (SURFACE background, BORDER outline, radius)."""
    inner = Table([[flowables]], colWidths=[18 * cm])
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


def _draw_page_frame(canvas, doc) -> None:
    """Full-page dark background + a quiet footer — the app never renders
    on a white page, so neither should its report."""
    canvas.saveState()
    canvas.setFillColor(BG)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.setFont("PlexSans", 7)
    canvas.setFillColor(TEXT3)
    canvas.drawString(1.5 * cm, 0.9 * cm, "Sedna Ops — Weekly Ops Report")
    canvas.drawRightString(A4[0] - 1.5 * cm, 0.9 * cm, f"Page {doc.page}")
    canvas.restoreState()


def render_pdf(snapshot: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.6 * cm, bottomMargin=1.6 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        title=f"Sedna Ops Weekly Ops Report — {snapshot['week']}",
    )
    ss = _styles()
    story = []
    full_w = 18 * cm

    # ── Cover + BLUF ────────────────────────────────────────────────────
    story.append(Paragraph("Sedna Ops", ss["Eyebrow"]))
    story.append(Paragraph("Weekly Ops Report", ss["ReportTitle"]))
    story.append(Paragraph(
        f"{snapshot['week']} &nbsp;·&nbsp; {snapshot['period_start']} to {snapshot['period_end']}",
        ss["ReportSub"],
    ))
    story.append(Spacer(1, 10))
    story.append(_card_wrap(ss, [Paragraph(snapshot["bluf"], ss["Bluf"])]))
    story.append(Spacer(1, 12))

    rag_tile_w = full_w / 5
    rag_tiles = []
    for area, status in snapshot["rag"].items():
        cell = Table(
            [[_p(area.upper(), ss["RagArea"])], [_p(status, ParagraphStyle("RagStatus", parent=ss["KpiValue"], fontSize=13, textColor=_RAG_TEXT.get(status, TEXT)))]],
            colWidths=[rag_tile_w - 0.15 * cm],
        )
        cell.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _RAG_BG.get(status, SURFACE2)),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER2),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
            ("TOPPADDING", (0, 1), (-1, 1), 2),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
        ]))
        rag_tiles.append(cell)
    story.append(_kpi_row(rag_tiles))
    story.append(PageBreak())

    # ── Support Cases ───────────────────────────────────────────────────
    sc = snapshot["support"]["scorecard"]
    story += _section_header(ss, "Support Cases", "Volume, response/resolution, case mix, and who's carrying what this week.")

    kpi_w = full_w / 6 - 0.2 * cm
    story.append(_kpi_row([
        _kpi_tile(ss, sc.get("logged_count"), "Logged", kpi_w),
        _kpi_tile(ss, sc.get("resolved_count"), "Resolved", kpi_w, accent=GREEN),
        _kpi_tile(ss, sc.get("fresh_resolved_count"), "Fresh Resolved", kpi_w),
        _kpi_tile(ss, len(sc.get("sla_breach_tickets") or []), "SLA Breaches", kpi_w, accent=RED if (sc.get("sla_breach_count") or 0) else None),
        _kpi_tile(ss, sc.get("replies_count"), "Replies", kpi_w),
        _kpi_tile(ss, sc.get("comments_count"), "Comments", kpi_w),
    ]))
    story.append(Spacer(1, 6))
    story.append(_kpi_row([
        _kpi_tile(ss, f"{sc['ttfr_median_hours']:.1f}h" if sc.get("ttfr_median_hours") is not None else "—", "TTFR Median", kpi_w),
        _kpi_tile(ss, f"{sc['ttr_median_hours']:.1f}h" if sc.get("ttr_median_hours") is not None else "—", "TTR Median", kpi_w),
        _kpi_tile(ss, f"{sc['median_time_to_first_move_hours']:.1f}h" if sc.get("median_time_to_first_move_hours") is not None else "—", "Time To First Move", kpi_w),
        _kpi_tile(ss, f"{sc['waiting_on_me_median_hours']:.1f}h" if sc.get("waiting_on_me_median_hours") is not None else "—", "Waiting-On-Me", kpi_w),
        _kpi_tile(ss, sc.get("open_load"), "Open Load (right now)", kpi_w),
        _kpi_tile(
            ss,
            f"{sc['open_load_vs_baseline_pct']:+.0f}%" if sc.get("open_load_vs_baseline_pct") is not None else "—",
            "vs. 28d Baseline", kpi_w,
            accent=(RED if (sc.get("open_load_vs_baseline_pct") or 0) > 0 else GREEN) if sc.get("open_load_vs_baseline_pct") is not None else None,
        ),
    ]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Team Breakdown — Logged / Assigned / Resolved / Replies / Comments", ss["SubHeading"]))
    by_eng = sc.get("by_engineer") or {}
    if by_eng:
        rows = []
        for name, m in by_eng.items():
            m = m or {}
            rows.append([name, m.get("logged", "—"), m.get("assigned", "—"), m.get("resolved", "—"), m.get("fresh_resolved", "—"), m.get("replies", "—"), m.get("comments", "—")])
        story.append(_table(
            ss, ["Engineer", "Logged", "Assigned", "Resolved", "Fresh Resolved", "Replies", "Comments"], rows,
            col_widths=[4 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm, 2.7 * cm, 2.2 * cm, 2.5 * cm],
        ))
    else:
        story.append(_empty(ss))

    story.append(Paragraph("Case Mix by Status", ss["SubHeading"]))
    case_mix = sc.get("case_mix") or []
    if case_mix:
        rows = [[cm.get("status"), cm.get("count"), cm.get("your_count")] for cm in case_mix]
        story.append(_table(ss, ["Status", "Count", "Yours"], rows, col_widths=[9 * cm, 4.5 * cm, 4.5 * cm]))
    else:
        story.append(_empty(ss))

    story.append(Paragraph("Aged Cases", ss["SubHeading"]))
    aged_cases = sc.get("aged_cases") or []
    if aged_cases:
        rows = [[a.get("label"), a.get("count"), ", ".join(a.get("example_refs") or []) or "—"] for a in aged_cases]
        story.append(_table(ss, ["Bucket", "Count", "Examples"], rows, col_widths=[4 * cm, 2.5 * cm, 11.5 * cm]))
    else:
        story.append(_empty(ss))

    story.append(Paragraph("Blocked Cases", ss["SubHeading"]))
    blocked = snapshot["support"]["blocked_cases"]
    if blocked:
        story.append(_table(
            ss, ["Ticket", "Customer", "Tier", "Reason"],
            [[b["jira_ref"], b["customer_name"] or "—", b["customer_tier"] or "—", b["blocked_reason"] or "—"] for b in blocked],
            col_widths=[2.5 * cm, 4 * cm, 2 * cm, 9.5 * cm],
        ))
    else:
        story.append(_empty(ss))
    story.append(PageBreak())

    # ── Bug Cases ───────────────────────────────────────────────────────
    ftr = snapshot["bugs"]["fix_to_relief"]
    story += _section_header(ss, "Bug Cases", "Fix-to-relief latency, real fleet exposure, and who's shipping the fixes.")
    ftr_w = full_w / 3 - 0.2 * cm
    story.append(_kpi_row([
        _kpi_tile(ss, f"{ftr.get('median_days')}d" if ftr.get("median_days") is not None else "—", "Fix→Relief Median", ftr_w),
        _kpi_tile(ss, f"{ftr.get('mean_days')}d" if ftr.get("mean_days") is not None else "—", "Fix→Relief Mean", ftr_w),
        _kpi_tile(ss, ftr.get("still_waiting_count", 0), "Still Waiting", ftr_w, accent=AMBER if ftr.get("still_waiting_count") else None),
    ]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Version Exposure — Reported vs. Silently Exposed (top 15 by exposure)", ss["SubHeading"]))
    ve = sorted(snapshot["bugs"]["version_exposure"], key=lambda v: -len(v["silently_exposed_customers"]))[:15]
    if ve:
        story.append(_table(
            ss, ["Bug", "Fix Version", "Assignee", "Reported", "Silently Exposed"],
            [[v["vms_ref"], v["fix_version"] or "—", v.get("assignee") or "—", len(v["reported_customers"]), len(v["silently_exposed_customers"])] for v in ve],
            col_widths=[3 * cm, 3 * cm, 5 * cm, 3 * cm, 4 * cm],
        ))
    else:
        story.append(_empty(ss))

    story.append(Paragraph("Engineer Impact", ss["SubHeading"]))
    ei = snapshot["bugs"]["engineer_impact"][:12]
    if ei:
        story.append(_table(
            ss, ["Engineer", "Bugs Fixed", "Customers Impacted", "Top Bug"],
            [[e["assignee"], e["bugs_fixed"], e["customers_impacted"], e["top_bug"] or "—"] for e in ei],
            col_widths=[5 * cm, 4 * cm, 5 * cm, 4 * cm],
        ))
    else:
        story.append(_empty(ss))

    story.append(Paragraph("Fixed, Not Yet Formally Released", ss["SubHeading"]))
    missing = snapshot["bugs"]["missing_releases"][:10]
    if missing:
        story.append(_table(
            ss, ["Fix Version", "Bugs", "Customers"],
            [[m["fix_version"], m["bug_count"], m["customer_count"]] for m in missing],
            col_widths=[6 * cm, 6 * cm, 6 * cm],
        ))
    else:
        story.append(_empty(ss))

    story.append(Paragraph("Bug-Fix Upgrades Overdue", ss["SubHeading"]))
    bfo = snapshot["bugs"]["bug_fix_upgrades_overdue"]
    if bfo:
        story.append(_table(
            ss, ["Ticket", "Customer", "Stage", "Days Stale"],
            [[u["jira_ref"] or "—", u["customer_name"] or "—", u["stage"], u["days_stale"]] for u in bfo],
            col_widths=[3 * cm, 7 * cm, 4 * cm, 4 * cm],
        ))
    else:
        story.append(_empty(ss))
    story.append(PageBreak())

    # ── Upgrade Cases ───────────────────────────────────────────────────
    pipeline = snapshot["upgrades"]["pipeline"]
    story += _section_header(ss, "Upgrade Cases", "Pipeline health — what's active, blocked, unconfirmed, or drifting.")

    up_w = full_w / 4 - 0.2 * cm
    story.append(_kpi_row([
        _kpi_tile(ss, pipeline.get("active_total"), "Active", up_w),
        _kpi_tile(ss, pipeline.get("blocked"), "Blocked", up_w, accent=RED if pipeline.get("blocked") else None),
        _kpi_tile(ss, pipeline.get("unconfirmed_slots"), "Unconfirmed Slots", up_w, accent=AMBER if pipeline.get("unconfirmed_slots") else None),
        _kpi_tile(ss, pipeline.get("done_this_month"), "Done This Month", up_w, accent=GREEN),
    ]))
    story.append(Spacer(1, 8))

    stages = pipeline.get("stages") or {}
    if stages:
        story.append(_table(ss, list(stages.keys()), [[len(v) for v in stages.values()]], col_widths=None))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Superseded (target already met)", ss["SubHeading"]))
    sup = snapshot["upgrades"]["superseded"]
    if sup:
        story.append(_table(
            ss, ["Ticket", "Customer", "Wants", "Already On"],
            [[s["jira_ref"] or "—", s["customer_name"] or "—", s["wants_version"], s["done_version"]] for s in sup],
            col_widths=[3 * cm, 7 * cm, 4 * cm, 4 * cm],
        ))
    else:
        story.append(_empty(ss))

    story.append(Paragraph("Unconfirmed (imminent/past-due)", ss["SubHeading"]))
    unc = snapshot["upgrades"]["unconfirmed"]
    if unc:
        story.append(_table(
            ss, ["Ticket", "Customer", "Stage", "DevOps", "Customer"],
            [[u["jira_ref"] or "—", u["customer_name"] or "—", u["stage"],
              "Yes" if u["devops_confirmed"] else "No", "Yes" if u["customer_confirmed"] else "No"] for u in unc],
            col_widths=[3 * cm, 6.5 * cm, 3.5 * cm, 2.5 * cm, 2.5 * cm],
        ))
    else:
        story.append(_empty(ss))

    story.append(Paragraph("Pending Upgrade — No Active Case", ss["SubHeading"]))
    pmc = snapshot["upgrades"]["pending_missing_case"]
    if pmc:
        story.append(_table(
            ss, ["Ticket", "Customer", "Environment", "Linked Bug"],
            [[c["jira_ref"] or "—", c["customer_name"] or "—", c["environment"], c["linked_vms_ref"] or "—"] for c in pmc],
            col_widths=[3 * cm, 7 * cm, 4 * cm, 4 * cm],
        ))
    else:
        story.append(_empty(ss))
    story.append(PageBreak())

    # ── Migration Cases ─────────────────────────────────────────────────
    mb = snapshot["migrations"]["board"]
    story += _section_header(ss, "Migration Cases", "Board funnel plus the priority bundling opportunities.")
    stage_counts = [[stage, len(rows)] for stage, rows in mb.get("stages", {}).items()]
    if stage_counts:
        story.append(_table(ss, ["Stage", "Count"], stage_counts, col_widths=[9 * cm, 9 * cm]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Migration Priority — Bundling Opportunities", ss["SubHeading"]))
    mp = snapshot["migrations"]["priority"].get("customers", [])[:15]
    if mp:
        story.append(_table(
            ss, ["Customer", "Tier", "Infra", "Stage", "Score", "Pending Defects", "Open Incidents"],
            [[m["customer_name"], m["customer_tier"] or "—", m.get("infra") or "—", m["migration_stage"], m["priority_score"],
              m["pending_upgrade_defect_count"], len(m["open_incident_remediations"])] for m in mp],
            col_widths=[4 * cm, 2 * cm, 2 * cm, 3 * cm, 2 * cm, 2.5 * cm, 2.5 * cm],
        ))
    else:
        story.append(_empty(ss))
    story.append(PageBreak())

    # ── Incidents ───────────────────────────────────────────────────────
    story += _section_header(ss, "Incidents", "Open product incidents and their per-customer remediation status.")
    open_incidents = snapshot["incidents"]["open"]
    if open_incidents:
        for inc in open_incidents:
            sev_hex = "#e8445a" if inc["severity"] in ("Critical", "High") else "#f0a030"
            story.append(Paragraph(
                f'<font color="{sev_hex}"><b>{inc["severity"]}</b></font> · {inc["phase"]} — {inc["title"]}',
                ss["SubHeading"],
            ))
            rems = inc.get("remediations", [])
            if rems:
                story.append(_table(
                    ss, ["Customer", "Tier", "Status"],
                    [[r["customer_name"] or "—", r["customer_tier"] or "—", r["derived_status"]] for r in rems],
                    col_widths=[7 * cm, 3 * cm, 8 * cm],
                ))
            else:
                story.append(_empty(ss, "No remediation rows tracked."))
    else:
        story.append(_empty(ss, "No open incidents."))
    story.append(PageBreak())

    # ── Customers at Risk ───────────────────────────────────────────────
    story += _section_header(ss, "Customers at Risk", "Customers currently hit by 2 or more real, independent signals.")
    car = snapshot["customers_at_risk"][:20]
    if car:
        story.append(_table(
            ss, ["Customer", "Tier", "# Signals", "Signals"],
            [[c["customer_name"] or "—", c["customer_tier"] or "—", len(c["signals"]), "; ".join(c["signals"][:4]) + (" …" if len(c["signals"]) > 4 else "")] for c in car],
            col_widths=[4 * cm, 2 * cm, 2 * cm, 10 * cm],
        ))
    else:
        story.append(_empty(ss, "No customer currently hit by 2 or more real signals."))

    doc.build(story, onFirstPage=_draw_page_frame, onLaterPages=_draw_page_frame)
    return buf.getvalue()
