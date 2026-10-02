"""
'My Desk' — the L2 engineer's home view.

Ticket-centric, not account-centric: six lanes answering "who has the
ball", plus a small set of workload KPIs. This router is the only place
that computes those numbers — nothing else re-derives them.
"""
import asyncio
import logging
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import settings
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.cancellation import Cancellation
from app.models.case import Case
from app.models.case_comment import CaseComment
from app.models.case_snapshot import DailyCaseSnapshot
from app.models.customer_tenant_info import CustomerTenantInfo
from app.models.customer import Customer
from app.models.migration_project import MigrationProject
from app.models.upgrade import Upgrade
from app.services.daily_ops import daily_ops_stats
from app.services.jira import (
    team_created_stats, team_open_stats, team_resolved_stats,
    _build_customer_match_maps, _resolve_customer_by_name_or_alias, _map_status,
)
from app.services.lanes import LANE_LABELS, compute_lanes, waiting_on
from app.services.time_windows import window_start
from app.services.upgrade_supervision import (
    overdue_bug_fix_upgrades, enrich_overdue_upgrade,
    unconfirmed_upgrades, enrich_unconfirmed_upgrade,
    pending_upgrades_missing_case, enrich_pending_upgrade_flag,
    superseded_upgrades,
)
from app.services.cert_scan import CERT_WARN_DAYS, days_until_expiry
from app.services.incident_supervision import stalled_incidents

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/desk", tags=["desk"])

_ACTIVE_MIGRATION_STAGES = {
    "Not Started", "Complete",
}
_RENEWAL_FLAG_DAYS = 60

# Real Jira display names for the three-person support team.
SUPPORT_TEAM = ["Asaph Mulaisi", "Gisele Wolff", "Yaseen Dolan"]
# Single source of truth for "who is using this app" on the backend side —
# mirrors frontend/src/config/team.ts's YOU constant exactly.
YOU = "Asaph Mulaisi"

# Rolling windows for the Team Load Split's resolved-cases/TTR period toggle.
_PERIOD_WINDOW_DAYS = {"day": 1, "week": 7, "month": 30, "quarter": 90, "year": 365}


def _hours(delta) -> float:
    return delta.total_seconds() / 3600


def _median_hours(deltas: list) -> float | None:
    hours = [_hours(d) for d in deltas if d is not None]
    return round(statistics.median(hours), 1) if hours else None


def _ttfr_hours(case: Case) -> float | None:
    """Prefer the native Initial Response SLA field; fall back to computed."""
    if case.ttfr_hours is not None:
        return case.ttfr_hours
    if case.first_public_reply_at and case.created_at:
        return (case.first_public_reply_at - case.created_at).total_seconds() / 3600
    return None


@dataclass
class _LiveCase:
    """Duck-types as a Case for waiting_on()/compute_lanes() AND
    desk_briefing()'s flag logic — same attributes both read, whether the
    ticket has a local Case row or not."""
    id: int | None
    jira_ref: str
    title: str
    priority: str
    case_type: str
    days_open: int
    status: str
    assigned_to: str | None
    last_mention_name: str | None
    # Real for a locally-matched ticket (Case.last_mention_at); None for a
    # live-only ticket with no local row yet — the bell's "being tagged"
    # notice only ever fires off a matched ticket's real timestamp, never
    # guesses a time for the unmatched case.
    last_mention_at: datetime | None
    lane_override: str | None
    escalated_at: datetime | None
    needs_csm_briefing: bool
    customer_id: int | None
    customer: Customer | None
    ttfr_breached: bool
    jira_customer_name: str | None
    # sla_days is confirmed dead for real tickets (only ever set by
    # seed.py's demo data, never by the live sync) — always None here,
    # matching what a real Case row already has in practice.
    sla_days: int | None
    # Real for a locally-matched ticket (Case.status_changed_at); None for a
    # live-only ticket with no local row yet — the queue-supervisor's
    # chase-needed check falls back to days_open as a coarser proxy in that
    # case, stated plainly rather than pretending the same precision.
    status_changed_at: datetime | None
    # Always sourced from the live Jira fetch (team_open_stats()'s by_status
    # entries), never from a local Case row — a Case never stores the raw
    # created timestamp or a live SLA countdown (the latter would go stale
    # the instant it's cached), so these two are populated from the same
    # live fetch regardless of whether the ticket has a local match. Powers
    # the My Desk Queue Table (see desk_queue() below).
    created: str | None
    sla: dict | None
    # Who replied most recently ("customer", a real team display name, or
    # None if the ticket has no comments yet) and when — always sourced
    # from the live Jira fetch (team_open_stats()'s by_status entries, via
    # _last_reply()), for BOTH matched and unmatched tickets, same reason
    # `created`/`sla` above are live-only: no local Case column tracks
    # this. Powers the My Desk Queue Table's "Last Update" column.
    last_reply_by: str | None
    last_reply_at: str | None
    # The real, un-collapsed Jira status name (e.g. "Defect / Enhancement
    # submitted", "Waiting for support", "Waiting for customer") — never
    # from a local Case row, which only ever stores the 3-bucket collapsed
    # status (Active/Awaiting Customer/Closed) via _map_status(). Always
    # available here since it's literally the loop key in
    # _live_open_cases() below, for both matched and unmatched tickets —
    # same "always live, never local" reasoning as created/sla/last_reply.
    # Exists purely for display/filtering (e.g. the Queue Table's Status
    # column) — the collapsed `status` above stays untouched everywhere
    # else (lane/alert logic keeps using the 3-bucket version).
    raw_status: str


async def _live_open_cases(db) -> list[_LiveCase]:
    """Every real open DSD ticket, live from Jira — not the local `cases`
    table alone, which only covers manually-mapped/auto-bridged tickets and
    confirmed-live undercounts real volume (a real engineer's Jira queue
    showed 61 open tickets against 32 this endpoint reported before this
    fix — the same class of gap already fixed for desk_team()/
    daily_ops_stats() earlier this session, never applied here).

    A ticket already mapped to a local Case row uses that row's real
    annotation fields (escalated_at, needs_csm_briefing, lane_override,
    last_mention_name) and its real customer relationship. A ticket with no
    local Case row yet still appears — resolved to a customer by name where
    possible, with id=None (no local PK to PATCH against) and every
    annotation field defaulting cleanly, which falls through waiting_on()'s
    priority chain the same way any case with no signal already does."""
    stats = await team_open_stats(db, SUPPORT_TEAM)
    local_result = await db.execute(
        select(Case).where(Case.status != "Closed").options(joinedload(Case.customer))
    )
    local_by_ref = {c.jira_ref: c for c in local_result.scalars().all()}
    customers_by_id, customers_by_normalized, by_alias = await _build_customer_match_maps(db)

    live: list[_LiveCase] = []
    for status_name, tickets in stats["by_status"].items():
        if status_name == "Pending Upgrade":
            continue  # Done-category in Jira, not genuinely open for the customer
        for t in tickets:
            local = local_by_ref.get(t["jira_ref"])
            if local:
                live.append(_LiveCase(
                    id=local.id, jira_ref=local.jira_ref, title=local.title,
                    priority=local.priority, case_type=local.case_type,
                    days_open=local.days_open, status=local.status,
                    assigned_to=local.assigned_to, last_mention_name=local.last_mention_name,
                    last_mention_at=local.last_mention_at,
                    lane_override=local.lane_override, escalated_at=local.escalated_at,
                    needs_csm_briefing=local.needs_csm_briefing,
                    customer_id=local.customer_id, customer=local.customer,
                    ttfr_breached=local.ttfr_breached, jira_customer_name=local.jira_customer_name,
                    sla_days=local.sla_days, status_changed_at=local.status_changed_at,
                    created=t["created"], sla=t["sla"],
                    last_reply_by=t["last_reply_by"], last_reply_at=t["last_reply_at"],
                    raw_status=status_name,
                ))
            else:
                customer = _resolve_customer_by_name_or_alias(
                    t["customer_name"], customers_by_normalized, by_alias, customers_by_id,
                )
                live.append(_LiveCase(
                    id=None, jira_ref=t["jira_ref"], title=t["title"],
                    priority=t["priority"], case_type=t["case_type"],
                    days_open=t["days_open"] or 0, status=_map_status(status_name),
                    assigned_to=t["assignee_name"], last_mention_name=None,
                    last_mention_at=None,
                    lane_override=None, escalated_at=None, needs_csm_briefing=False,
                    customer_id=customer.id if customer else None, customer=customer,
                    ttfr_breached=t["ttfr_breached"], jira_customer_name=t["customer_name"],
                    sla_days=None, status_changed_at=None,
                    created=t["created"], sla=t["sla"],
                    last_reply_by=t["last_reply_by"], last_reply_at=t["last_reply_at"],
                    raw_status=status_name,
                ))
    return live


@router.get("/lanes")
async def desk_lanes(db: AsyncSession = Depends(get_db)):
    cases = await _live_open_cases(db)

    migrating_result = await db.execute(
        select(MigrationProject.customer_id).where(
            MigrationProject.stage.notin_(_ACTIVE_MIGRATION_STAGES)
        ).distinct()
    )
    migrating_customer_ids = set(migrating_result.scalars().all())

    lanes = compute_lanes(cases)
    today = date.today()

    for lane in lanes["lanes"]:
        rows = []
        for c in lane["cases"]:
            renewal_days = (
                (c.customer.renewal_date - today).days if c.customer and c.customer.renewal_date else None
            )
            hypercare_until = c.customer.hypercare_until if c.customer else None
            rows.append({
                "id": c.id,
                "jira_ref": c.jira_ref,
                "title": c.title,
                "priority": c.priority,
                "days_open": c.days_open,
                "status": c.status,
                "assigned_to": c.assigned_to,
                "last_mention_name": c.last_mention_name,
                "lane_override": c.lane_override,
                "customer_id": c.customer_id,
                "customer_name": c.customer.name if c.customer else None,
                "tier": c.customer.tier if c.customer else None,
                "csm": c.customer.csm if c.customer else None,
                "renewal_flag": renewal_days is not None and 0 <= renewal_days <= _RENEWAL_FLAG_DAYS,
                "migration_flag": c.customer_id in migrating_customer_ids,
                "hypercare_flag": hypercare_until is not None,
                "hypercare_overdue": hypercare_until is not None and today > hypercare_until,
                "hypercare_reason": c.customer.hypercare_reason if c.customer else None,
            })
        # Hypercare cases bubble to the top of their lane regardless of age —
        # the actual "flag it for prioritization" mechanism, not just a chip.
        rows.sort(key=lambda r: (not r["hypercare_flag"], -r["days_open"]))
        lane["rows"] = rows
        del lane["cases"]

    return lanes


@router.get("/queue")
async def desk_queue(db: AsyncSession = Depends(get_db)):
    """A flat, sortable/filterable queue table for My Desk — every real open
    DSD ticket (live Jira, same _live_open_cases() source as desk_lanes()),
    one row each, with the real Initial-Response SLA countdown and lane
    classification alongside the ticket-level facts. Distinct from
    desk_lanes(): that view answers "who's carrying what," grouped by lane;
    this one answers "show me every ticket," as a single searchable list —
    same underlying data, a different lens. All filtering/sorting happens
    client-side over this one fetch, matching how Customer Risk Queue's
    filters already work on My Desk."""
    cases = await _live_open_cases(db)
    rows = []
    for c in cases:
        rows.append({
            "id": c.id,
            "jira_ref": c.jira_ref,
            "title": c.title,
            "customer_id": c.customer_id,
            "customer_name": c.customer.name if c.customer else c.jira_customer_name,
            "customer_tier": c.customer.tier if c.customer else None,
            "priority": c.priority,
            "status": c.status,
            "raw_status": c.raw_status,
            "assigned_to": c.assigned_to,
            "created": c.created,
            "days_open": c.days_open,
            "sla": c.sla,
            "lane": waiting_on(c),
            "lane_label": LANE_LABELS[waiting_on(c)],
            "last_reply_by": c.last_reply_by,
            "last_reply_at": c.last_reply_at,
        })
    return {"total": len(rows), "rows": rows}


@router.get("/summary")
async def desk_summary(db: AsyncSession = Depends(get_db)):
    today = date.today()
    window_start = today - timedelta(days=28)

    snap_result = await db.execute(
        select(DailyCaseSnapshot)
        .where(DailyCaseSnapshot.customer_id.is_(None), DailyCaseSnapshot.snapshot_date >= window_start)
        .order_by(DailyCaseSnapshot.snapshot_date)
    )
    snapshots = snap_result.scalars().all()

    calibrating = len(snapshots) < 7
    baseline = round(statistics.mean(s.open_count for s in snapshots)) if snapshots else None

    # Open Load comes live from Jira — same reasoning as desk_team: the
    # local `cases` table only covers tickets a human has manually mapped
    # to a customer, undercounting real open workload by ~10x. This has to
    # match whatever scale the baseline above is calibrated on, or the
    # vs-baseline% is comparing two different things — see team_open_stats'
    # docstring and the snapshot-recalc job in scheduler.py, which now
    # writes the global baseline row from this same live source.
    open_source = "jira_live"
    try:
        if not settings.jira_enabled:
            raise RuntimeError("Jira disabled")
        open_stats = await team_open_stats(db, SUPPORT_TEAM)
        open_count = open_stats["total_open"]
        updated_today = open_stats["total_updated_today"]
    except Exception as exc:
        logger.error("Live Jira open-stats fetch failed, falling back to local data: %s", exc)
        open_source = "local_fallback"
        open_result = await db.execute(select(Case).where(Case.status != "Closed"))
        open_count = len(open_result.scalars().all())
        day_start_fallback = datetime(today.year, today.month, today.day)
        updated_today_result = await db.execute(select(Case).where(Case.updated_at >= day_start_fallback))
        updated_today = len(updated_today_result.scalars().all())

    open_vs_baseline_pct = (
        round((open_count - baseline) / baseline * 100) if baseline else None
    )

    last7_start = today - timedelta(days=7)
    recent_snaps = [s for s in snapshots if s.snapshot_date >= last7_start]
    arrivals_7d = sum(s.created_count for s in recent_snaps)
    closures_7d = sum(s.closed_count for s in recent_snaps)

    moved_result = await db.execute(
        select(Case).where(
            Case.status_changed_at.is_not(None),
            Case.created_at >= datetime.utcnow() - timedelta(days=30),
        )
    )
    moved_cases = moved_result.scalars().all()
    move_hours = [
        (c.status_changed_at - c.created_at).total_seconds() / 3600
        for c in moved_cases if c.status_changed_at and c.created_at
    ]
    median_time_to_first_move = round(statistics.median(move_hours), 1) if move_hours else None

    month_start = datetime.utcnow() - timedelta(days=30)
    ttfr_result = await db.execute(
        select(Case).where(Case.created_at >= month_start, Case.status != "Closed")
    )
    ttfr_pool = ttfr_result.scalars().all()
    ttfr_hours_list = [_ttfr_hours(c) for c in ttfr_pool]
    ttfr_hours_list = [h for h in ttfr_hours_list if h is not None]
    ttfr_median = round(statistics.median(ttfr_hours_list), 1) if ttfr_hours_list else None
    ttfr_breach_count = sum(1 for c in ttfr_pool if c.ttfr_breached)

    # Resolved-count/TTR come live from Jira — same reasoning as desk_team:
    # the local `cases` table only holds tickets a human has manually
    # mapped to a customer, which structurally excludes most real resolved
    # tickets. Fall back to the (undercounted) local numbers if Jira is
    # unreachable/disabled rather than fail the whole summary.
    try:
        if not settings.jira_enabled:
            raise RuntimeError("Jira disabled")
        month_stats, today_stats = await asyncio.gather(
            team_resolved_stats(db, SUPPORT_TEAM, days=30),
            team_resolved_stats(db, SUPPORT_TEAM, days=1),
        )
        ttr_median = month_stats["total_ttr_median_hours"]
        resolved_today = today_stats["total_resolved"]
    except Exception as exc:
        logger.error("Live Jira resolved-stats fetch failed, falling back to local data: %s", exc)
        ttr_result = await db.execute(
            select(Case).where(Case.resolved_at.is_not(None), Case.resolved_at >= month_start)
        )
        ttr_cases = ttr_result.scalars().all()
        ttr_median = _median_hours([c.resolved_at - c.created_at for c in ttr_cases])

        day_start = datetime(today.year, today.month, today.day)
        resolved_today_result = await db.execute(
            select(Case).where(Case.resolved_at.is_not(None), Case.resolved_at >= day_start)
        )
        resolved_today = len(resolved_today_result.scalars().all())

    return {
        "open_load": open_count,
        "open_load_source": open_source,
        "open_load_baseline": baseline,
        "open_load_vs_baseline_pct": open_vs_baseline_pct,
        "calibrating": calibrating,
        "arrivals_7d": arrivals_7d,
        "closures_7d": closures_7d,
        "median_time_to_first_move_hours": median_time_to_first_move,
        "closed_last_7_days": closures_7d,
        "ttfr_median_hours": ttfr_median,
        "ttfr_breach_count": ttfr_breach_count,
        "ttr_median_hours": ttr_median,
        "resolved_today": resolved_today,
        "updated_today": updated_today,
    }


@router.get("/daily-series")
async def desk_daily_series(days: int = 30, db: AsyncSession = Depends(get_db)):
    """Real day-by-day open/created/closed counts (global rows, customer_id
    IS NULL) — the raw series behind Command Center's sparklines. Previously
    this data only ever got reduced to a single baseline mean (desk_summary's
    open_load_baseline); this exposes the actual series for the first time."""
    start = date.today() - timedelta(days=days)
    result = await db.execute(
        select(DailyCaseSnapshot)
        .where(DailyCaseSnapshot.customer_id.is_(None), DailyCaseSnapshot.snapshot_date >= start)
        .order_by(DailyCaseSnapshot.snapshot_date)
    )
    snapshots = result.scalars().all()
    return {
        "days": [
            {
                "date": s.snapshot_date.isoformat(),
                "open_count": s.open_count,
                "created_count": s.created_count,
                "closed_count": s.closed_count,
            }
            for s in snapshots
        ]
    }


@router.get("/daily-ops")
async def desk_daily_ops(days: int = 30, db: AsyncSession = Depends(get_db)):
    """The real "measure my daily ops" view — Assigned/Resolved/Replies/
    Comments, per SUPPORT_TEAM engineer, per day. The single shared source
    for this data (see services/daily_ops.py) — Command Center's window
    aggregate reads from the exact same function rather than re-deriving
    any of these four numbers separately.
    """
    if not settings.jira_enabled:
        return {"days": days, "series": [], "totals": {n: {"assigned": 0, "fresh_assigned": 0, "resolved": 0, "fresh_resolved": 0, "opened": 0, "replies": 0, "comments": 0} for n in SUPPORT_TEAM}, "fetched_at": None, "source": "unavailable"}
    try:
        stats = await daily_ops_stats(db, SUPPORT_TEAM, days)
    except Exception as exc:
        logger.error("daily_ops_stats failed: %s", exc)
        return {"days": days, "series": [], "totals": {n: {"assigned": 0, "fresh_assigned": 0, "resolved": 0, "fresh_resolved": 0, "opened": 0, "replies": 0, "comments": 0} for n in SUPPORT_TEAM}, "fetched_at": None, "source": "unavailable"}
    return {**stats, "source": "jira_live"}


def _month_bounds(month: str) -> tuple[date, date]:
    """'YYYY-MM' -> (first day of that month, first day of the next month)."""
    year, mon = (int(p) for p in month.split("-"))
    start = date(year, mon, 1)
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    return start, end


def _age_days(cases: list[Case]) -> tuple[float | None, float | None]:
    """Mean/median age, in days, of currently-open cases — the complement
    to TTR: TTR only speaks about cases that have already resolved, so a
    stale backlog can sit invisible for months and then distort TTR all at
    once the moment it finally gets closed (confirmed live: this is exactly
    what happened when Gisele closed a batch of month-old-plus backlog
    tickets in one sweep). Tracking open-case age directly surfaces that
    staleness continuously instead of only after the fact."""
    now = datetime.now(timezone.utc)
    ages = [(now - c.created_at).total_seconds() / 86400 for c in cases if c.created_at]
    if not ages:
        return None, None
    return round(statistics.mean(ages), 1), round(statistics.median(ages), 1)


@router.get("/team")
async def desk_team(period: str = "week", month: str | None = None, db: AsyncSession = Depends(get_db)):
    """Real workload split across the three-person support team, from Jira assignee.

    `period` (day/week/month/quarter/year) controls the rolling window for
    the resolved-cases count and its TTR — the two figures where "since
    when" actually changes the answer. quarter/year were added specifically
    so Command Center's own Week/Month/Quarter/Year toggle can drive this
    endpoint directly instead of the two staying out of sync (confirmed
    live: the page's toggle used to silently do nothing to this data).
    Open/updated-today/TTFR/open-case-age stay on their own fixed windows
    (open is a live snapshot, TTFR tracks response to recently-created
    tickets) since a period toggle aimed at "how many did we close" would
    otherwise silently reshape unrelated numbers too. Team Load Split's own
    donut/table are the one exception: they additionally get an
    `_in_window` variant (open tickets CREATED within `period_start`) so
    that panel specifically can respect the toggle — see team_open_stats'
    docstring for why the always-live open count is unfair to use there on
    its own (it silently rewards whoever has the largest historical
    backlog, on every single period, regardless of how quickly they
    actually resolve new work).

    `month` (optional, "YYYY-MM") overrides `period` with a fixed calendar
    month instead of a rolling window — "last month" needs to mean an
    actual stable month you can compare against, not a shifting lookback.
    """
    period = period if period in _PERIOD_WINDOW_DAYS else "week"

    today = date.today()
    week_start = datetime.utcnow() - timedelta(days=7)
    month_start = month_end = None
    if month:
        try:
            month_start, month_end = _month_bounds(month)
        except (ValueError, TypeError):
            month = None
    # "month"/"year" are calendar-to-date here, matching command_center.py's
    # own window_start() — this used to be a rolling 30/365-day window
    # instead, silently disagreeing with Command Center's definition of the
    # same label (confirmed live: materially different TTR/TTFR for "month"
    # on the two pages). "day"/"week"/"quarter" stay rolling windows — week
    # and quarter already numerically match window_start's own rolling-7/
    # rolling-90, and window_start has no "day" concept at all.
    period_start = (
        datetime(month_start.year, month_start.month, month_start.day) if month_start
        else window_start(period) if period in ("month", "year")
        else datetime.utcnow() - timedelta(days=_PERIOD_WINDOW_DAYS[period])
    )

    def _ttfr_for(cases: list[Case]) -> float | None:
        hours = [_ttfr_hours(c) for c in cases]
        hours = [h for h in hours if h is not None]
        return round(statistics.median(hours), 1) if hours else None

    # Open/age/updated-today/TTFR and Resolved/TTR both come live from Jira,
    # not the local `cases` table — that table only holds tickets a human
    # has manually mapped to a customer, which undercounts real workload
    # badly (confirmed live: 566 real open DSD tickets vs 59 local; see
    # team_open_stats' and team_resolved_stats' docstrings). Each falls back
    # to the local, undercounted numbers independently if Jira is
    # unreachable/disabled, rather than failing the whole request.
    open_source = "jira_live"
    try:
        if not settings.jira_enabled:
            raise RuntimeError("Jira disabled")
        open_stats = await team_open_stats(db, SUPPORT_TEAM, since=period_start)
    except Exception as exc:
        logger.error("Live Jira open-stats fetch failed, falling back to local data: %s", exc)
        open_source = "local_fallback"
        open_result = await db.execute(select(Case).where(Case.status != "Closed"))
        open_cases = open_result.scalars().all()
        day_start = datetime(today.year, today.month, today.day)
        updated_today_result = await db.execute(select(Case).where(Case.updated_at >= day_start))
        updated_today_cases = updated_today_result.scalars().all()
        ttfr_result = await db.execute(select(Case).where(Case.created_at >= week_start))
        ttfr_cases = ttfr_result.scalars().all()
        team_age_mean, team_age_median = _age_days(open_cases)
        # Windowed mirror of open_cases, matching the live path's "created
        # on/after period_start, still open" definition — same reasoning
        # (Team Load Split shouldn't reward whoever's sat on the largest
        # backlog longest), just against the local, undercounted table
        # since this is the already-degraded fallback path.
        open_cases_window = [c for c in open_cases if c.created_at and c.created_at >= period_start.replace(tzinfo=timezone.utc)]
        window_age_mean, window_age_median = _age_days(open_cases_window)

        def _open_ticket(c: Case) -> dict:
            age = (datetime.now(timezone.utc) - c.created_at).days if c.created_at else None
            return {
                "jira_ref": c.jira_ref, "title": c.title, "assignee_name": c.assigned_to,
                "customer_name": c.jira_customer_name, "days_open": age,
            }

        by_engineer = {}
        for name in SUPPORT_TEAM:
            age_mean, age_median = _age_days([c for c in open_cases if c.assigned_to == name])
            window_cases_for_name = [c for c in open_cases_window if c.assigned_to == name]
            age_mean_w, age_median_w = _age_days(window_cases_for_name)
            by_engineer[name] = {
                "open": sum(1 for c in open_cases if c.assigned_to == name),
                "open_age_mean_days": age_mean,
                "open_age_median_days": age_median,
                "updated_today": sum(1 for c in updated_today_cases if c.assigned_to == name),
                "ttfr_median_hours": _ttfr_for([c for c in ttfr_cases if c.assigned_to == name]),
                "open_in_window": len(window_cases_for_name),
                "open_age_mean_days_in_window": age_mean_w,
                "open_age_median_days_in_window": age_median_w,
            }
        open_stats = {
            "total_open": len(open_cases),
            "total_open_age_mean_days": team_age_mean,
            "total_open_age_median_days": team_age_median,
            "total_updated_today": len(updated_today_cases),
            "total_ttfr_median_hours": _ttfr_for(ttfr_cases),
            "unassigned_open": sum(1 for c in open_cases if not c.assigned_to),
            "other_open": sum(1 for c in open_cases if c.assigned_to and c.assigned_to not in SUPPORT_TEAM),
            "by_engineer": by_engineer,
            "total_open_in_window": len(open_cases_window),
            "total_open_age_mean_days_in_window": window_age_mean,
            "total_open_age_median_days_in_window": window_age_median,
            "unassigned_open_in_window": sum(1 for c in open_cases_window if not c.assigned_to),
            "other_open_in_window": sum(1 for c in open_cases_window if c.assigned_to and c.assigned_to not in SUPPORT_TEAM),
            "tickets_by_engineer_in_window": {
                name: [_open_ticket(c) for c in open_cases_window if c.assigned_to == name]
                for name in SUPPORT_TEAM
            },
        }

    resolved_source = "jira_live"
    try:
        if not settings.jira_enabled:
            raise RuntimeError("Jira disabled")
        if month_start and month_end:
            resolved_stats = await team_resolved_stats(db, SUPPORT_TEAM, start=month_start, end=month_end)
        elif period in ("month", "year"):
            resolved_stats = await team_resolved_stats(
                db, SUPPORT_TEAM, start=window_start(period).date(), end=date.today() + timedelta(days=1)
            )
        else:
            resolved_stats = await team_resolved_stats(db, SUPPORT_TEAM, days=_PERIOD_WINDOW_DAYS[period])
    except Exception as exc:
        logger.error("Live Jira resolved-stats fetch failed, falling back to local data: %s", exc)
        resolved_source = "local_fallback"
        resolved_result = await db.execute(
            select(Case).where(Case.resolved_at.is_not(None), Case.resolved_at >= period_start)
        )
        resolved_cases = resolved_result.scalars().all()

        def _ttfr_median(cases: list[Case]) -> float | None:
            hours = [h for h in (_ttfr_hours(c) for c in cases) if h is not None]
            return round(statistics.median(hours), 1) if hours else None

        def _case_ticket(c: Case) -> dict:
            days = (c.resolved_at - c.created_at).days if c.resolved_at and c.created_at else None
            return {
                "jira_ref": c.jira_ref, "title": c.title, "assignee_name": c.assigned_to,
                "customer_name": c.jira_customer_name, "days_open": days,
            }

        resolved_stats = {
            "total_resolved": len(resolved_cases),
            "total_ttr_median_hours": _median_hours([c.resolved_at - c.created_at for c in resolved_cases]),
            "total_ttfr_median_hours": _ttfr_median(resolved_cases),
            "by_engineer": {
                name: {
                    "resolved": sum(1 for c in resolved_cases if c.assigned_to == name),
                    "ttr_median_hours": _median_hours([
                        c.resolved_at - c.created_at for c in resolved_cases if c.assigned_to == name
                    ]),
                    "ttfr_median_hours": _ttfr_median([c for c in resolved_cases if c.assigned_to == name]),
                    # fresh/backlog split needs real Jira comment/changelog
                    # history — not available on this local-fallback path,
                    # so these stay null rather than a fabricated value.
                    "ttr_median_hours_fresh": None,
                    "ttr_median_hours_backlog": None,
                    "ttfr_median_hours_fresh": None,
                    "ttfr_median_hours_backlog": None,
                    "fresh_resolved": None,
                }
                for name in SUPPORT_TEAM
            },
            "tickets_by_engineer": {
                name: [_case_ticket(c) for c in resolved_cases if c.assigned_to == name]
                for name in SUPPORT_TEAM
            },
        }

    # Created-in-window count, per engineer — the denominator Team Load
    # Split's donut/legend needs to turn "10 still open" into a
    # self-anchored rate ("10 of 39 opened this week are still open")
    # instead of a raw count that only means something next to a
    # neighbor's slice. Deliberately the CURRENT assignee of a ticket
    # created in this window (team_created_stats' own convention, same as
    # team_open_stats) — a ticket reassigned since creation counts toward
    # whoever holds it now, matching how every other per-engineer figure on
    # this endpoint already works.
    created_source = "jira_live"
    try:
        if not settings.jira_enabled:
            raise RuntimeError("Jira disabled")
        if month_start and month_end:
            created_stats = await team_created_stats(SUPPORT_TEAM, start=month_start, end=month_end)
        elif period in ("month", "year"):
            created_stats = await team_created_stats(
                SUPPORT_TEAM, start=window_start(period).date(), end=date.today() + timedelta(days=1)
            )
        else:
            created_stats = await team_created_stats(SUPPORT_TEAM, days=_PERIOD_WINDOW_DAYS[period])
    except Exception as exc:
        logger.error("Live Jira created-stats fetch failed, falling back to local data: %s", exc)
        created_source = "local_fallback"
        created_result = await db.execute(select(Case).where(Case.created_at >= period_start))
        created_cases = created_result.scalars().all()

        def _created_ticket(c: Case) -> dict:
            age = (datetime.now(timezone.utc) - c.created_at).days if c.created_at else None
            return {
                "jira_ref": c.jira_ref, "title": c.title, "assignee_name": c.assigned_to,
                "customer_name": c.jira_customer_name, "days_open": age,
            }

        created_stats = {
            "total_created": len(created_cases),
            "by_engineer": {
                name: {"created": sum(1 for c in created_cases if c.assigned_to == name)}
                for name in SUPPORT_TEAM
            },
            "tickets_by_engineer": {
                name: [_created_ticket(c) for c in created_cases if c.assigned_to == name]
                for name in SUPPORT_TEAM
            },
        }

    engineers = [
        {
            "name": name,
            **open_stats["by_engineer"][name],
            **resolved_stats["by_engineer"][name],
            **created_stats["by_engineer"][name],
            # Real per-ticket detail behind Open/Created/Resolved, for Team
            # Load Split's drillable cells — reuses the ticket lists each
            # underlying stats function already builds (no new fetch here).
            "tickets_open": open_stats["tickets_by_engineer_in_window"][name],
            "tickets_created": created_stats["tickets_by_engineer"][name],
            "tickets_resolved": resolved_stats["tickets_by_engineer"][name],
        }
        for name in SUPPORT_TEAM
    ]

    team_total = {
        "open": open_stats["total_open"],
        "open_age_mean_days": open_stats["total_open_age_mean_days"],
        "open_age_median_days": open_stats["total_open_age_median_days"],
        "resolved": resolved_stats["total_resolved"],
        "updated_today": open_stats["total_updated_today"],
        # Windowed (resolved_stats), not open_stats' all-currently-open-
        # tickets figure — see the fix note on team_resolved_stats' new
        # per-engineer ttfr_median_hours above; same bug existed here too.
        "ttfr_median_hours": resolved_stats["total_ttfr_median_hours"],
        "ttr_median_hours": resolved_stats["total_ttr_median_hours"],
        "open_in_window": open_stats["total_open_in_window"],
        "open_age_mean_days_in_window": open_stats["total_open_age_mean_days_in_window"],
        "open_age_median_days_in_window": open_stats["total_open_age_median_days_in_window"],
        # Team-wide "created this window" denominator — scoped the same way
        # as open_in_window (every DSD ticket, not just the named team), so
        # the two are directly comparable as a team-level still-open rate.
        # Named "created" (not "created_in_window") to match the same key
        # each per-engineer dict uses — team_total is spread through the
        # same DeskEngineer shape as every individual engineer.
        "created": created_stats["total_created"],
        # Team-total drill lists are the 3 named engineers' own tickets
        # concatenated — NOT the full unfiltered total_open/total_created
        # count above (which also includes unassigned/other-engineer
        # tickets project-wide). Same "named roster" scope as every
        # per-engineer list; the frontend labels this row accordingly
        # rather than implying full project-wide coverage.
        "tickets_open": [t for name in SUPPORT_TEAM for t in open_stats["tickets_by_engineer_in_window"][name]],
        "tickets_created": [t for name in SUPPORT_TEAM for t in created_stats["tickets_by_engineer"][name]],
        "tickets_resolved": [t for name in SUPPORT_TEAM for t in resolved_stats["tickets_by_engineer"][name]],
    }

    # Live (unwindowed) ticket detail behind the Unassigned/Other flags —
    # "needs triage" is urgent regardless of when a ticket arrived, so this
    # stays live rather than windowed like Open/Created/Resolved above.
    # Sourced from team_open_stats' by_status (already fetched, real detail
    # across every open ticket) on the live path; rebuilt from the local
    # table on the degraded fallback path.
    if "by_status" in open_stats:
        all_open_tickets = [t for tickets in open_stats["by_status"].values() for t in tickets]
        unassigned_tickets = [t for t in all_open_tickets if not t["assignee_name"]]
        other_tickets = [t for t in all_open_tickets if t["assignee_name"] and t["assignee_name"] not in SUPPORT_TEAM]
    else:
        unassigned_tickets = [_open_ticket(c) for c in open_cases if not c.assigned_to]
        other_tickets = [_open_ticket(c) for c in open_cases if c.assigned_to and c.assigned_to not in SUPPORT_TEAM]

    return {
        "period": period,
        "month": month,
        "resolved_source": resolved_source,
        "open_source": open_source,
        "created_source": created_source,
        "team": team_total,
        "engineers": engineers,
        "unassigned_open": open_stats["unassigned_open"],
        "other_open": open_stats["other_open"],
        "unassigned_open_in_window": open_stats["unassigned_open_in_window"],
        "other_open_in_window": open_stats["other_open_in_window"],
        "unassigned_tickets": unassigned_tickets,
        "other_tickets": other_tickets,
    }


@router.get("/briefing")
async def desk_briefing(since: str | None = None, scope: str = "team", db: AsyncSession = Depends(get_db)):
    """Flags, Needs-a-Decision-Today, and the activity feed since a given timestamp.

    Flags/decisions now read from _live_open_cases() (live Jira, not just
    the local table) — same fix as desk_lanes(), same confirmed undercount
    (SLA Breaches showed 25/team-97 against a real, larger queue before this).

    `scope` ("me" | "team") only governs the queue-supervisor flags added
    below (stale/chase-needed/blocked-upgrade) — the pre-existing
    sla_breach_* fields stay team-wide exactly as before, since the
    frontend already does its own client-side me-vs-team split for those
    ("Your SLA Breaches" vs "team: N") and re-scoping them here would
    silently break that already-working contract."""
    cases = await _live_open_cases(db)
    today = date.today()

    # Flags
    sla_flagged = [c for c in cases if c.ttfr_breached or (c.sla_days and c.days_open > c.sla_days)]
    # Deduped by customer, not by case — a customer's renewal risk is a
    # per-account fact, not one per open ticket. Confirmed live this
    # mattered once _live_open_cases() started surfacing a real customer's
    # full ticket volume instead of the local table's undercount: an
    # 8-ticket account showed up 8 times in the same list before this fix.
    renewal_flagged_customers: dict[int, Customer] = {}
    for c in cases:
        if c.customer and c.customer.renewal_date and 0 <= (c.customer.renewal_date - today).days <= 60:
            renewal_flagged_customers[c.customer.id] = c.customer
    renewal_flagged = list(renewal_flagged_customers.values())
    stalled_migrations = (
        (await db.execute(
            select(MigrationProject).where(MigrationProject.stalled == True)  # noqa: E712
            .options(joinedload(MigrationProject.customer))
        ))
        .scalars().all()
    )
    overdue_cancellations = [
        c for c in (await db.execute(
            select(Cancellation).where(Cancellation.stage != "Decommissioned").options(joinedload(Cancellation.customer))
        )).scalars().all()
        if today > c.effective_date
    ]
    hypercare_customers = (
        (await db.execute(select(Customer).where(Customer.hypercare_until.is_not(None))))
        .scalars().all()
    )
    # Genuinely per-host, not per-account like renewal_under_60d — gb-prod
    # and gb-test are two different certs with two different expiry dates,
    # so no per-customer dedup here. Error rows (DNS failure etc.) are
    # deliberately excluded from the count below — a probe failure is a
    # data-quality problem visible on the Engineering tab, not a renewal
    # reminder, and including it would inflate a number read as "certs I
    # need to renew."
    cert_cutoff = datetime.now(timezone.utc) + timedelta(days=CERT_WARN_DAYS)
    expiring_certs = (
        (await db.execute(
            select(CustomerTenantInfo)
            .where(
                CustomerTenantInfo.cert_expires_at.is_not(None),
                CustomerTenantInfo.cert_expires_at <= cert_cutoff,
            )
            .options(joinedload(CustomerTenantInfo.customer))
        )).scalars().all()
    )
    expiring_certs.sort(key=lambda t: t.cert_expires_at)
    overdue_bug_fix = await overdue_bug_fix_upgrades(db)
    unconfirmed = await unconfirmed_upgrades(db)
    pending_missing_case = await pending_upgrades_missing_case(db)
    superseded = await superseded_upgrades(db)
    stalled_incs = await stalled_incidents(db)

    # Queue Supervisor — reuses the already-fetched `cases` list (no second
    # live-Jira round trip) and the same predicates alerts.py's scheduled
    # job runs, so "what's live on the page" and "what the 15-min job would
    # alert on" can never drift into two different answers.
    from app.services.alerts import is_stale_case, chase_needed_days, chase_overdue_days, reply_missed_days, latest_customer_replies
    scoped_cases = [c for c in cases if c.assigned_to == YOU] if scope == "me" else cases
    stale_cases = [c for c in scoped_cases if is_stale_case(c)]
    awaiting_refs = [c.jira_ref for c in scoped_cases if c.status == "Awaiting Customer"]
    latest_reply = await latest_customer_replies(db, awaiting_refs)
    chase_cases = [(c, chase_needed_days(c, latest_reply)) for c in scoped_cases if chase_needed_days(c, latest_reply) is not None]
    chase_overdue_cases = [(c, chase_overdue_days(c, latest_reply)) for c in scoped_cases if chase_overdue_days(c, latest_reply) is not None]
    reply_missed_cases = [(c, reply_missed_days(c, latest_reply)) for c in scoped_cases if reply_missed_days(c, latest_reply) is not None]
    blocked_upgrades_result = await db.execute(
        select(Upgrade).where(Upgrade.blocked == True, Upgrade.stage != "Verified Done")  # noqa: E712
        .options(joinedload(Upgrade.customer))
    )
    blocked_upgrades = blocked_upgrades_result.scalars().all()

    # Bell-only signals, both genuinely day-scoped (unlike stale/chase-needed,
    # which are inherently multi-day thresholds with no honest "happened in
    # the last 24h" reading — those stay Queue-Supervisor-only, never fed to
    # the bell). "Mentioned" fires off a real Case.last_mention_at; "recent
    # comments" reads the CaseComment cache built by the Jira Activity tab
    # (services/jira.py::fetch_case_activity) — real data, but only as
    # complete as which cases someone has actually opened that tab for, not
    # a global comment feed yet. Both stated plainly to the frontend/user
    # rather than presented as more complete than they are.
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    mentioned_tickets = [
        {
            "jira_ref": c.jira_ref, "title": c.title,
            "customer_name": c.customer.name if c.customer else c.jira_customer_name,
            "assignee_name": c.assigned_to, "mentioned_name": c.last_mention_name,
            "days_open": c.days_open,
        }
        for c in cases
        if c.last_mention_at and c.last_mention_at >= day_ago
    ]
    recent_comments_result = await db.execute(
        select(CaseComment, Case)
        .join(Case, CaseComment.case_id == Case.id)
        .where(CaseComment.created >= day_ago)
        .options(joinedload(Case.customer))
        .order_by(CaseComment.created.desc())
    )
    recent_comments = [
        {
            "jira_ref": case.jira_ref, "author": comment.author,
            "created": comment.created.isoformat(),
            "text": comment.text[:200],
            "customer_name": case.customer.name if case.customer else None,
            "assignee_name": case.assigned_to,
        }
        for comment, case in recent_comments_result.all()
    ]

    def _sla_ticket(c: Case) -> dict:
        return {
            "jira_ref": c.jira_ref, "title": c.title, "assignee_name": c.assigned_to,
            "customer_name": c.customer.name if c.customer else c.jira_customer_name,
            "days_open": c.days_open,
        }

    flags = {
        "sla_breach_count": len(sla_flagged),
        "sla_breach_refs": [c.jira_ref for c in sla_flagged[:5]],
        # Full ticket-level detail (all of them, not just the sample above)
        # so the flag tile can drill into every breaching ticket, not just
        # the first 3-5 named inline.
        "sla_breach_tickets": [_sla_ticket(c) for c in sla_flagged],
        "renewal_under_60d_count": len(renewal_flagged),
        "renewal_under_60d_customers": [
            {"id": c.id, "name": c.name} for c in renewal_flagged
        ],
        "stalled_migration_count": len(stalled_migrations),
        "stalled_migrations": [
            {"id": m.id, "customer_id": m.customer_id, "customer_name": m.customer.name if m.customer else None}
            for m in stalled_migrations
        ],
        "cancellation_overdue_count": len(overdue_cancellations),
        "cancellation_overdue_customers": [
            {"id": c.customer.id, "name": c.customer.name} for c in overdue_cancellations if c.customer
        ],
        "hypercare_count": len(hypercare_customers),
        "hypercare_customers": [{"id": c.id, "name": c.name} for c in hypercare_customers],
        "certs_expiring_count": len(expiring_certs),
        "certs_expiring": [
            {
                "id": t.id,
                "customer_id": t.customer_id,
                "customer_name": t.customer.name if t.customer else None,
                "environment": t.environment,
                "subdomain": t.subdomain,
                "expires_at": t.cert_expires_at,
                "days_until_expiry": days_until_expiry(t.cert_expires_at),
                "issuer": t.cert_issuer,
            }
            for t in expiring_certs
        ],
        "bug_fix_upgrade_overdue_count": len(overdue_bug_fix),
        "bug_fix_upgrade_overdue": [enrich_overdue_upgrade(u) for u in overdue_bug_fix],
        "unconfirmed_upgrade_count": len(unconfirmed),
        "unconfirmed_upgrades": [enrich_unconfirmed_upgrade(u) for u in unconfirmed],
        "pending_upgrade_missing_case_count": len(pending_missing_case),
        "pending_upgrade_missing_case": [enrich_pending_upgrade_flag(c) for c in pending_missing_case],
        # An active Upgrade whose target version is already met/exceeded —
        # by another completed Upgrade row or the customer's real synced
        # tenant version (see superseded_upgrades() for the Peak People AS
        # incident this half of the check exists for). Always team-wide,
        # same reasoning as blocked_upgrade_count below — Upgrade has no
        # assignee/creator field to scope by.
        "superseded_upgrade_count": len(superseded),
        "superseded_upgrades": superseded,
        "stalled_incident_count": len(stalled_incs),
        "stalled_incidents": stalled_incs,
        # Bell-only, last-24h signals — see the comment above their computation.
        "mentioned_count": len(mentioned_tickets),
        "mentioned_tickets": mentioned_tickets,
        "recent_comment_count": len(recent_comments),
        "recent_comments": recent_comments,
        # Queue Supervisor — scope-aware (see `scope` param above).
        "stale_count": len(stale_cases),
        "stale_tickets": [_sla_ticket(c) for c in stale_cases],
        "chase_needed_count": len(chase_cases),
        "chase_needed_tickets": [{**_sla_ticket(c), "days_waiting": days} for c, days in chase_cases],
        "chase_overdue_count": len(chase_overdue_cases),
        "chase_overdue_tickets": [{**_sla_ticket(c), "days_waiting": days} for c, days in chase_overdue_cases],
        "reply_missed_count": len(reply_missed_cases),
        "reply_missed_tickets": [{**_sla_ticket(c), "days_since_reply": days} for c, days in reply_missed_cases],
        # Always team-wide — Upgrade has no assignee/creator field to scope by.
        "blocked_upgrade_count": len(blocked_upgrades),
        "blocked_upgrades": [
            {
                "id": u.id, "jira_ref": u.jira_ref, "customer_id": u.customer_id,
                "customer_name": u.customer.name if u.customer else None,
                "blocked_reason": u.blocked_reason,
            }
            for u in blocked_upgrades
        ],
    }

    # Needs a Decision Today — templated over real thresholds, not AI.
    # Hypercare customers go first, always — a human specifically flagged
    # them for close attention, which outranks a generic stale-ticket
    # heuristic every time. Confirmed live this was a real gap: hypercare
    # already drove the Flags row and the State-of-Play sentence, but this
    # list itself never looked at it, so a real hypercare account could sit
    # invisible here behind a 2000-day-old ticket nobody's actively working.
    decisions = []
    for hc in hypercare_customers:
        hc_cases = [c for c in cases if c.customer and c.customer.id == hc.id]
        overdue = hc.hypercare_until is not None and hc.hypercare_until < today
        if overdue:
            text = f"{hc.name}'s hypercare window ended {(today - hc.hypercare_until).days}d ago — still flagged, still needs a call."
        else:
            text = f"{hc.name} is in hypercare — {len(hc_cases)} open case(s) need close attention."
            if hc.hypercare_until:
                text += f" Window ends {hc.hypercare_until.isoformat()}."
        decisions.append({
            "text": text,
            "detail": hc.hypercare_reason or "No reason on file",
            "jira_ref": hc_cases[0].jira_ref if hc_cases else None,
        })

    oldest = max(cases, key=lambda c: c.days_open, default=None)
    if oldest and oldest.days_open > 90:
        decisions.append({
            "text": f"{oldest.jira_ref} has been open {oldest.days_open} days with no resolution.",
            "detail": f"{oldest.customer.name if oldest.customer else 'Unknown'} · {waiting_on(oldest)}",
            "jira_ref": oldest.jira_ref,
        })
    blocked_escalated = [c for c in cases if c.escalated_at]
    if blocked_escalated:
        top = max(blocked_escalated, key=lambda c: c.days_open)
        decisions.append({
            "text": f"{top.jira_ref} is escalated to Gisele and still open.",
            "detail": f"{top.customer.name if top.customer else 'Unknown'} · {top.days_open}d open",
            "jira_ref": top.jira_ref,
        })
    if cases:
        by_customer: dict[str, int] = {}
        for c in cases:
            name = c.jira_customer_name or (c.customer.name if c.customer else "Unknown")
            by_customer[name] = by_customer.get(name, 0) + 1
        top_customer, top_count = max(by_customer.items(), key=lambda kv: kv[1])
        share = round(top_count / len(cases) * 100)
        if share >= 20:
            decisions.append({
                "text": f"{top_customer} accounts for {share}% of your open load on its own.",
                "detail": f"{top_count} of {len(cases)} open tickets",
                "jira_ref": None,
            })

    # Activity feed
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except Exception:
            since_dt = None
    if since_dt is None:
        since_dt = datetime.utcnow() - timedelta(hours=12)

    events = (
        (await db.execute(
            select(AuditLog).where(AuditLog.created_at >= since_dt).order_by(AuditLog.created_at.desc()).limit(20)
        )).scalars().all()
    )

    return {
        "flags": flags,
        "needs_decision": decisions,
        "activity": [
            {"time": e.created_at, "action": e.action, "target": e.target_id, "detail": e.detail}
            for e in events
        ],
    }
