"""
Daily digest and on-demand snapshot (C7).

Morning brief  — 08:45 Europe/London → Haiku generates compact text → Slack.
Full snapshot  — on-demand via POST /snapshot/trigger or the dashboard button.

When ANTHROPIC_API_KEY is set, Haiku writes natural language.
Without it, a clean template-based format is used — nothing breaks.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.case import Case
from app.models.customer import Customer
from app.models.migration_project import MigrationProject
from app.models.ops_note import OpsNote
from app.models.release import Release
from app.models.upgrade import Upgrade
from app.models.vms_bug import VmsBug
from app.services import rovo

logger = logging.getLogger(__name__)


async def _build_state(db) -> dict:
    case_result = await db.execute(
        select(Case).where(Case.status != "Closed").options(joinedload(Case.customer))
    )
    cases = case_result.scalars().all()

    sla_breaching = [c for c in cases if c.sla_days and c.days_open > c.sla_days]
    blocked_cases = [c for c in cases if c.blocked]
    stale = [c for c in cases if c.days_open >= 12]
    oldest = max(cases, key=lambda c: c.days_open) if cases else None

    upg_result = await db.execute(
        select(Upgrade)
        .where(Upgrade.stage != "Verified Done")
        .options(joinedload(Upgrade.customer))
    )
    upgrades = upg_result.scalars().all()

    mig_result = await db.execute(select(MigrationProject))
    migrations = mig_result.scalars().all()

    cust_result = await db.execute(
        select(Customer)
        .where(Customer.product.ilike("%VMS%"))
        .options(selectinload(Customer.cases))
    )
    customers = cust_result.scalars().all()

    high_risk = [
        c for c in customers
        if any(
            case.sla_days and case.days_open > case.sla_days
            for case in c.cases
            if case.status != "Closed"
        )
    ]

    return {
        "total_open": len(cases),
        "sla_breaching": sla_breaching,
        "blocked_cases": blocked_cases,
        "stale": stale,
        "oldest": oldest,
        "upgrades_active": len(upgrades),
        "upgrades_blocked": sum(1 for u in upgrades if u.blocked),
        "migrations_total": len(migrations),
        "migrations_complete": sum(1 for m in migrations if m.stage == "Complete"),
        "high_risk": high_risk,
        "ts": datetime.now(timezone.utc),
    }


def _morning_template(s: dict) -> str:
    day = s["ts"].strftime("%a %d %b %Y")
    oldest_line = ""
    if s["oldest"]:
        o = s["oldest"]
        cname = o.customer.name if o.customer else "Unknown"
        oldest_line = f"\nOldest: {o.jira_ref} · {cname} · {o.days_open}d · {o.status}"
    return (
        f"📊 Queue Brief — {day}\n"
        f"Queue: {s['total_open']} open · {len(s['sla_breaching'])} SLA breaching · "
        f"{len(s['stale'])} stale (12d+)"
        f"{oldest_line}\n"
        f"Upgrades: {s['upgrades_active']} active · {s['upgrades_blocked']} blocked\n"
        f"Auto-brief · Sedna Ops"
    )


def _snapshot_template(s: dict) -> str:
    ts = s["ts"].strftime("%a %d %b %Y · %H:%M UTC")
    lines = [f"📋 Full Queue Snapshot — {ts}"]

    if s["high_risk"]:
        lines.append("🔴 High Risk")
        for c in s["high_risk"]:
            active = [case for case in c.cases if case.status != "Closed"]
            breaching = [case for case in active if case.sla_days and case.days_open > case.sla_days]
            lines.append(f"  · {c.name} — {len(breaching)} breaching · {len(active)} active")

    lines.append(
        f"📊 Queue: {s['total_open']} open · "
        f"{len(s['sla_breaching'])} breaching SLA · {len(s['blocked_cases'])} blocked"
    )
    lines.append(
        f"🔧 Upgrades: {s['upgrades_active']} active · {s['upgrades_blocked']} blocked"
    )
    lines.append(
        f"☁️ Migrations: {s['migrations_complete']}/{s['migrations_total']} on new AWS"
    )
    return "\n".join(lines)


async def _haiku(prompt: str) -> str | None:
    if not settings.ai_enabled:
        return None
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as exc:
        logger.error("Haiku call failed: %s", exc)
        return None


CLAUDE_HANDOVER_MODEL = "claude-haiku-4-5"


async def claude_chat_reply(messages: list[dict], system: str | None = None) -> str | None:
    """Multi-turn Claude call for the Ollama chat "escalate to Claude"
    handover (routers/ollama_chat.py) — same client/model/error-handling
    shape as _haiku() above, just a real messages array + optional system
    block instead of one flattened prompt string. Same graceful-degradation
    contract: returns None on any failure or when AI is disabled, never
    raises past this function."""
    if not settings.ai_enabled:
        return None
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        kwargs: dict = {"model": CLAUDE_HANDOVER_MODEL, "max_tokens": 1024, "messages": messages}
        if system:
            kwargs["system"] = system
        msg = await client.messages.create(**kwargs)
        return msg.content[0].text.strip()
    except Exception as exc:
        logger.error("Claude handover call failed: %s", exc)
        return None


async def morning_brief() -> str:
    """Generate and post the morning brief. Returns the posted text."""
    async with AsyncSessionLocal() as db:
        state = await _build_state(db)

    template = _morning_template(state)

    if settings.ai_enabled:
        ai = await _haiku(
            "Write a concise Slack morning brief for a shipping software support team. "
            "Under 5 lines, plain text, no markdown. Data:\n\n" + template
        )
        text = ai or template
    else:
        text = template

    from app.services.slack import post as slack_post
    await slack_post(text)
    logger.info("Morning brief posted (%d chars)", len(text))
    return text


# Bound Rovo lookups deliberately — a customer summary can cover dozens of
# cases, and calling out to the Teamwork Graph once per case would be both
# slow and, once these tools leave beta, real metered Rovo-credit cost.
# Only the worst few get the live enrichment; every case still gets the
# free, already-computed local context below regardless.
_MAX_ROVO_LOOKUPS = 3


async def _known_bug_status(ref: str | None, db, releases_by_version: dict[str, Release]) -> str | None:
    """'Already fixed and released' vs. 'fixed, not yet released' vs. 'still
    being worked, sprint X' — reuses the exact matched-release logic
    pending_upgrade_queue() already established (routers/releases.py), not a
    re-derivation of it."""
    if not ref:
        return None
    bug = (await db.execute(select(VmsBug).where(VmsBug.jira_ref == ref))).scalar_one_or_none()
    if not bug:
        return None
    if bug.fix_version:
        matched = releases_by_version.get(bug.fix_version)
        if matched:
            return f"{ref}: fixed in {matched.version}, already released."
        if bug.status == "Done":
            return f"{ref}: fixed (target {bug.fix_version}), not yet formally released."
        return f"{ref}: fix targets {bug.fix_version}, still in progress ({bug.status})."
    sprint = f", {bug.sprint_name}" if bug.sprint_name else ""
    return f"{ref}: {bug.status}{sprint}, no fix version confirmed yet."


async def _related_case_fanout(case: Case, db) -> str | None:
    """How many other real tickets touch the same underlying thing — reuses
    the same related_case_refs split/lookup pattern already established in
    routers/cases.py::get_case_by_ref."""
    refs = [r for r in (case.related_case_refs or "").split(",") if r]
    if not refs:
        return None
    matched = (await db.execute(select(Case).where(Case.jira_ref.in_(refs)))).scalars().all()
    others = sorted({c.jira_customer_name for c in matched if c.jira_customer_name})
    if others:
        return f"{case.jira_ref}: related to {len(refs)} other ticket(s), also affecting {', '.join(others)}."
    return f"{case.jira_ref}: related to {len(refs)} other ticket(s)."


async def _ops_notes_context(jira_ref: str | None, db) -> str | None:
    """Real, manually-pasted human context (Slack discussion etc. — see
    OpsNote's own docstring: no Slack API access exists, so this is a
    paste-in log, not a live sync) tagged to this specific ref. Confirmed
    no auto-parsing is attempted — a human tags these by hand."""
    if not jira_ref:
        return None
    notes = (await db.execute(select(OpsNote).where(OpsNote.jira_ref == jira_ref))).scalars().all()
    if not notes:
        return None
    return f"{jira_ref}: " + " / ".join(n.text for n in notes)


async def _build_case_context(case: Case, db, releases_by_version: dict[str, Release], use_rovo: bool) -> str | None:
    """One case's enrichment block — local data (free, already computed)
    plus optional live Rovo context (bounded, see _MAX_ROVO_LOOKUPS).
    Every piece is independently optional; a case with none of this still
    summarizes fine on its title/priority/age alone."""
    parts = [p for p in (
        await _known_bug_status(case.linked_vms_ref, db, releases_by_version),
        await _related_case_fanout(case, db),
        f"{case.jira_ref}: {case.rovo_context}" if case.rovo_context else None,
        await _ops_notes_context(case.jira_ref, db),
    ) if p]
    if use_rovo and settings.rovo_enabled:
        rovo_context = await rovo.get_teamwork_context(case.jira_ref)
        if rovo_context:
            parts.append(f"{case.jira_ref}: linked work found — {rovo_context}")
    return "\n  ".join(parts) if parts else None


async def summarize_customer_issues(customer_name: str, cases: list[Case], db=None) -> str | None:
    """AI summary of what one customer has been reporting. None if AI disabled.

    `db` is optional only so existing non-DB callers (if any show up later)
    degrade to the old title-only behavior rather than breaking outright —
    every real call site today has a session available and should pass it.
    """
    if not settings.ai_enabled:
        return None
    if not cases:
        return f"No open or recent tickets from {customer_name}."

    context_lines = ""
    if db is not None:
        releases_by_version = {
            r.version.replace("-R", ""): r for r in (await db.execute(select(Release))).scalars().all()
        }
        # Worst-first bounding: High priority, then oldest — matches the
        # same "surface the worst, not everything" convention release_defects()
        # already uses (multi-customer-impact bugs sorted first).
        rovo_eligible = sorted(cases, key=lambda c: (c.priority != "High", -c.days_open))[:_MAX_ROVO_LOOKUPS]
        rovo_refs = {c.jira_ref for c in rovo_eligible}
        blocks = [
            await _build_case_context(c, db, releases_by_version, use_rovo=c.jira_ref in rovo_refs)
            for c in cases
        ]
        context_lines = "\n".join(f"  {b}" for b in blocks if b)

    lines = "\n".join(f"- [{c.case_type}, {c.priority}] {c.title} ({c.jira_ref}, {c.days_open}d open)" for c in cases)
    extra = f"\n\nAdditional known context:\n{context_lines}" if context_lines else ""
    return await _haiku(
        f"Summarize what the customer '{customer_name}' has been reporting to support, based on "
        f"these tickets. Focus on: whether this is one real pattern or several unrelated issues, "
        f"whether anything is already fixed and where that fix currently sits, and any related work "
        f"found elsewhere. 3-5 sentences, plain text, no markdown, no preamble. "
        f"Tickets:\n\n{lines}{extra}"
    )


async def summarize_bug_impact(bug_ref: str, customers: list[str], cases: list[Case], db=None) -> str | None:
    """AI summary of the common thread across multiple customers hitting the same bug."""
    if not settings.ai_enabled:
        return None
    if not cases:
        return None

    extra = ""
    if db is not None:
        releases_by_version = {
            r.version.replace("-R", ""): r for r in (await db.execute(select(Release))).scalars().all()
        }
        status_line = await _known_bug_status(bug_ref, db, releases_by_version)
        bug_row = (await db.execute(select(VmsBug).where(VmsBug.jira_ref == bug_ref))).scalar_one_or_none()
        pasted_context = bug_row.rovo_context if bug_row and bug_row.rovo_context else None
        rovo_context = await rovo.get_teamwork_context(bug_ref) if settings.rovo_enabled else None
        ops_context = await _ops_notes_context(bug_ref, db)
        parts = [p for p in (
            status_line,
            pasted_context,
            f"Linked work found — {rovo_context}" if rovo_context else None,
            ops_context,
        ) if p]
        if parts:
            extra = "\n\nAdditional known context:\n  " + "\n  ".join(parts)

    lines = "\n".join(f"- {c.jira_customer_name or 'Unknown'}: {c.title}" for c in cases)
    return await _haiku(
        f"These support tickets from different customers are all linked to the same underlying "
        f"defect ({bug_ref}), affecting: {', '.join(customers)}. Summarize the common thread — "
        f"what's actually going wrong from the customers' point of view, and whether it's already "
        f"fixed and where that fix currently sits. 3-5 sentences, plain text, no markdown. "
        f"Tickets:\n\n{lines}{extra}"
    )


async def full_snapshot() -> str:
    """Generate and post the full snapshot. Returns the posted text."""
    async with AsyncSessionLocal() as db:
        state = await _build_state(db)

    template = _snapshot_template(state)

    if settings.ai_enabled:
        ai = await _haiku(
            "Write a structured Slack digest for a support manager. "
            "Cover high-risk customers, queue stats, upgrades, migrations. "
            "Under 12 lines, plain text. Data:\n\n" + template
        )
        text = ai or template
    else:
        text = template

    from app.services.slack import post as slack_post
    await slack_post(text)
    logger.info("Full snapshot posted (%d chars)", len(text))
    return text
