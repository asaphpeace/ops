"""Queue supervisor — real "needs attention" checks, shared by two consumers:

1. `run()` — the scheduled job (every 15 min via APScheduler), team-wide,
   posts to Slack with a 4-hour cooldown. Currently a no-op delivery-wise
   (SLACK_WEBHOOK_URL isn't configured) but stays real, working
   infrastructure for whenever it is.
2. `compute_alerts()` — the pure computation, also called live (no
   cooldown, no Slack) by `desk_briefing()`'s own in-app "Needs Attention"
   section, since Slack has nowhere to post today. One set of rules, two
   consumers — not two diverging implementations of "is this stale."

Ticket-level checks (stale, chase-needed) go through `_live_open_cases()`
(desk.py) — the same real live-Jira source already fixing the local-table
undercount everywhere else in this app — and can be scoped to one engineer
via `scope="me"`. Blocked-upgrade checks stay team-wide always: `Upgrade`
has no assignee/creator field to scope by yet.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.database import AsyncSessionLocal
from app.models.audit_log import AuditLog
from app.models.case_comment import CaseComment
from app.models.customer import Customer
from app.models.upgrade import Upgrade

logger = logging.getLogger(__name__)

_last_fired: dict[str, datetime] = {}
_COOLDOWN = timedelta(hours=4)


def _should_fire(key: str) -> bool:
    last = _last_fired.get(key)
    if last and (datetime.now(timezone.utc) - last) < _COOLDOWN:
        return False
    _last_fired[key] = datetime.now(timezone.utc)
    return True


async def _reload_cooldowns() -> None:
    """Reload recent alert firings from DB into the in-memory cache.
    Called at the start of each run() cycle so restarts don't lose cooldown state."""
    cutoff = datetime.now(timezone.utc) - _COOLDOWN
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AuditLog.target_id, AuditLog.created_at).where(
                AuditLog.action == "alert_fired",
                AuditLog.created_at >= cutoff,
            )
        )
        for row in result.all():
            key, fired_at = row.target_id, row.created_at
            if key and (key not in _last_fired or fired_at > _last_fired[key]):
                _last_fired[key] = fired_at


def is_stale_case(c) -> bool:
    """14d+ sitting in Awaiting Dev with no resolution. Duck-types against
    either a real Case row or desk.py's _LiveCase — same attribute names."""
    return c.status == "Awaiting Dev" and c.days_open >= 14


async def latest_customer_replies(db, jira_refs: list[str]) -> dict[str, datetime]:
    """Real customer-authored comment timestamps, keyed by jira_ref — the
    max `created` per ref among comments whose author_account_type is
    confirmed "customer" (never a NULL/unconfirmed row, and never a team
    member's own customer-visible reply — confirmed live that jsdPublic
    alone isn't reliable for this, see CaseComment.author_account_type's
    own docstring). This is what lets a genuinely-silent Awaiting-Customer
    case be told apart from one where the customer already replied and
    nobody's acted on it since."""
    if not jira_refs:
        return {}
    result = await db.execute(
        select(CaseComment.jira_ref, func.max(CaseComment.created))
        .where(CaseComment.jira_ref.in_(jira_refs), CaseComment.author_account_type == "customer")
        .group_by(CaseComment.jira_ref)
    )
    return dict(result.all())


def reply_missed_days(c, latest_reply: dict[str, datetime]) -> int | None:
    """Days since a real customer-authored comment landed AFTER this
    case's status last changed — the customer already answered, but the
    status was never flipped off Awaiting Customer to reflect it, so this
    is now stuck on OUR side, not theirs. Needs a real status_changed_at
    (a locally-matched Case); a live-only ticket with no local row has no
    reliable baseline to compare against, so this always returns None for
    those rather than guessing. Fires from day 1 (not a 2-week grace
    window like chase_needed/chase_overdue below) — an unread reply is
    actionable immediately, not something to sit on."""
    if c.status != "Awaiting Customer":
        return None
    status_changed_at = getattr(c, "status_changed_at", None)
    if not status_changed_at:
        return None
    reply_at = latest_reply.get(c.jira_ref)
    if not reply_at or reply_at <= status_changed_at:
        return None
    days = (datetime.now(timezone.utc) - reply_at).days
    return days if days >= 1 else None


def chase_needed_days(c, latest_reply: dict[str, datetime]) -> int | None:
    """Days since this ticket entered Awaiting Customer, when in [5, 14) —
    14d+ escalates to chase_overdue_days() instead (a separate, harder
    alert type) rather than this one just growing an ever-larger day count
    with no visual distinction. Returns None when the customer already
    replied after status_changed_at — that's reply_missed_days()'s job,
    not this one's, since the case isn't genuinely "awaiting" anymore.
    Prefers the real status_changed_at when available (a locally-matched
    Case); falls back to days_open — a coarser proxy — for a live-only
    ticket with no local row yet. Stated plainly: the fallback isn't the
    same precision."""
    if reply_missed_days(c, latest_reply) is not None:
        return None
    if c.status != "Awaiting Customer":
        return None
    if getattr(c, "status_changed_at", None):
        days = (datetime.now(timezone.utc) - c.status_changed_at).days
    else:
        days = c.days_open
    return days if 5 <= days < 14 else None


def chase_overdue_days(c, latest_reply: dict[str, datetime]) -> int | None:
    """14d+ genuinely silent in Awaiting Customer — chase_needed's harder,
    separately-alerted escalation tier (own alert type, not just a bigger
    number inside chase_needed, so it doesn't blend into the same visual
    weight as a 6-day-old case). Mutually exclusive with both
    chase_needed_days (day-range split at 14) and reply_missed_days (a
    real customer reply since status changed means this isn't "on them"
    anymore)."""
    if reply_missed_days(c, latest_reply) is not None:
        return None
    if c.status != "Awaiting Customer":
        return None
    if getattr(c, "status_changed_at", None):
        days = (datetime.now(timezone.utc) - c.status_changed_at).days
    else:
        days = c.days_open
    return days if days >= 14 else None


async def compute_alerts(db, scope: str = "team") -> list[dict]:
    """Pure computation — no side effects, no cooldown, no Slack. Every
    alert is a structured dict, not a pre-formatted string, so a consumer
    (Slack text, or a real in-app drill-list) can render it however it needs."""
    from app.routers.desk import _live_open_cases, YOU

    cases = await _live_open_cases(db)
    if scope == "me":
        cases = [c for c in cases if c.assigned_to == YOU]

    awaiting_refs = [c.jira_ref for c in cases if c.status == "Awaiting Customer"]
    latest_reply = await latest_customer_replies(db, awaiting_refs)

    alerts: list[dict] = []
    for c in cases:
        cname = c.customer.name if c.customer else (c.jira_customer_name or "Unknown")
        if c.ttfr_breached:
            alerts.append({
                "type": "sla_breach", "jira_ref": c.jira_ref, "customer_name": cname,
                "detail": f"{c.days_open}d open, initial response SLA breached", "assignee_name": c.assigned_to,
            })
        if is_stale_case(c):
            alerts.append({
                "type": "stale", "jira_ref": c.jira_ref, "customer_name": cname,
                "detail": f"{c.days_open}d with no dev resolution", "assignee_name": c.assigned_to,
            })
        chase_days = chase_needed_days(c, latest_reply)
        if chase_days is not None:
            alerts.append({
                "type": "chase_needed", "jira_ref": c.jira_ref, "customer_name": cname,
                "detail": f"{chase_days}d awaiting customer response", "assignee_name": c.assigned_to,
            })
        overdue_days = chase_overdue_days(c, latest_reply)
        if overdue_days is not None:
            alerts.append({
                "type": "chase_overdue", "jira_ref": c.jira_ref, "customer_name": cname,
                "detail": f"{overdue_days}d awaiting customer response, still no reply", "assignee_name": c.assigned_to,
            })
        reply_days = reply_missed_days(c, latest_reply)
        if reply_days is not None:
            alerts.append({
                "type": "reply_missed", "jira_ref": c.jira_ref, "customer_name": cname,
                "detail": f"customer replied {reply_days}d ago, still marked Awaiting Customer", "assignee_name": c.assigned_to,
            })

    upg_result = await db.execute(
        select(Upgrade).where(Upgrade.blocked == True, Upgrade.stage != "Verified Done")  # noqa: E712
        .options(joinedload(Upgrade.customer))
    )
    for upg in upg_result.scalars().all():
        cname = upg.customer.name if upg.customer else "Unknown"
        alerts.append({
            "type": "blocked_upgrade", "jira_ref": upg.jira_ref, "customer_name": cname,
            "detail": upg.blocked_reason or "no reason given", "upgrade_id": upg.id, "assignee_name": None,
        })

    return alerts


async def _renewal_alerts(db) -> list[dict]:
    today = date.today()
    alerts = []
    cust_result = await db.execute(select(Customer))
    for cust in cust_result.scalars().all():
        if cust.renewal_date:
            days_left = (cust.renewal_date - today).days
            if 0 < days_left <= 30:
                alerts.append({
                    "type": "renewal", "jira_ref": None, "customer_name": cust.name,
                    "detail": f"renewal in {days_left}d", "assignee_name": None,
                })
    return alerts


_ALERT_KEY_FIELD = {
    "sla_breach": "jira_ref", "stale": "jira_ref", "chase_needed": "jira_ref",
    "chase_overdue": "jira_ref", "reply_missed": "jira_ref",
    "blocked_upgrade": "upgrade_id", "renewal": "customer_name",
}
_ALERT_EMOJI = {
    "sla_breach": "⚠️", "stale": "🕓", "chase_needed": "📬", "chase_overdue": "🚨",
    "reply_missed": "📨", "blocked_upgrade": "🔧", "renewal": "📅",
}


def _format_alert(a: dict) -> str:
    ref = a.get("jira_ref") or ""
    label = f"{ref} ({a['customer_name']})" if ref else a["customer_name"]
    return f"{_ALERT_EMOJI[a['type']]} {a['type'].replace('_', ' ').title()}: {label} — {a['detail']}"


async def run() -> None:
    """Scheduled entry point — every 15 min, team-wide, cooldown-deduped,
    posts to Slack (a real no-op today since SLACK_WEBHOOK_URL isn't set;
    stays ready for when it is)."""
    await _reload_cooldowns()

    async with AsyncSessionLocal() as db:
        all_alerts = await compute_alerts(db, scope="team")
        all_alerts += await _renewal_alerts(db)

        to_fire = []
        fired_keys = []
        for a in all_alerts:
            key_field = _ALERT_KEY_FIELD[a["type"]]
            key = f"{a['type']}:{a[key_field]}"
            if _should_fire(key):
                to_fire.append(a)
                fired_keys.append(key)

        if not to_fire:
            logger.debug("Alert engine: no new alerts this cycle")
            return

        for key in fired_keys:
            db.add(AuditLog(actor="system", action="alert_fired", target_type="alert", target_id=key))
        await db.commit()

    from app.services.slack import post as slack_post
    logger.info("Alert engine: %d alert(s) firing", len(to_fire))
    await slack_post("\n".join(_format_alert(a) for a in to_fire))
