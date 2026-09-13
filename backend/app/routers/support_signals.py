"""
'Support Signals' — analytical view. Nothing here needs an action today;
it's for spotting patterns across the whole open queue.
"""
import statistics
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import settings
from app.database import get_db
from app.models.case import Case
from app.models.case_snapshot import DailyCaseSnapshot
from app.services.jira import real_open_counts_by_customer, real_resolved_stats, team_open_stats
from app.services.lanes import SUPPORT_TEAM

router = APIRouter(prefix="/support-signals", tags=["support-signals"])

_AGING_BUCKETS = [
    ("0-7 days", 0, 7),
    ("8-30 days", 8, 30),
    ("31-90 days", 31, 90),
    ("91-365 days", 91, 365),
    ("over 1 year", 366, None),
]

_EXCHANGE_THRESHOLD = 5


@router.get("/aging")
async def aging_buckets(db: AsyncSession = Depends(get_db)):
    """Real, live-Jira age buckets — reuses team_open_stats()'s already-
    fetched, already-cached `by_status` data (no new Jira fetch) instead of
    the local `cases` table, same undercount reason as every other Support
    Signals endpoint fixed this session (a real customer showed 13 open
    locally vs. 95 real). "Pending Upgrade" tickets are excluded, matching
    team_open_stats()'s own total_open_count exclusion — they're Done-
    category in Jira and not genuinely sitting in the aging support queue.
    """
    days_open_values: list[int] = []
    source = "jira_live"
    if settings.jira_enabled:
        try:
            stats = await team_open_stats(db, list(SUPPORT_TEAM))
            for status_name, tickets in stats["by_status"].items():
                if status_name == "Pending Upgrade":
                    continue
                days_open_values.extend(t["days_open"] for t in tickets if t["days_open"] is not None)
        except Exception:
            source = "local_fallback"
    else:
        source = "local_fallback"

    if source == "local_fallback":
        result = await db.execute(select(Case).where(Case.status != "Closed"))
        days_open_values = [c.days_open for c in result.scalars().all()]

    total = len(days_open_values) or 1
    buckets = []
    for label, lo, hi in _AGING_BUCKETS:
        rows = [d for d in days_open_values if d >= lo and (hi is None or d <= hi)]
        buckets.append({
            "label": label,
            "count": len(rows),
            "share_pct": round(len(rows) / total * 100),
        })

    over_90 = sum(1 for d in days_open_values if d > 90)
    return {"total_open": len(days_open_values), "over_90_days": over_90, "buckets": buckets, "source": source}


@router.get("/volume")
async def volume_trend(db: AsyncSession = Depends(get_db)):
    """Current open count is real, live-Jira (real_open_counts_by_customer)
    rather than the local `cases` table — confirmed live that table
    undercounts real per-customer open volume the same way it undercounts
    everything else built on it (a real customer showed 13 locally vs. 95
    real open). The 4-week baseline stays local-table-sourced (DailyCase
    Snapshot's per-customer rows) — there's no way to retroactively know
    what Jira looked like on past days, only what today's snapshot job
    writes going forward. That job was fixed alongside this endpoint (see
    scheduler.py::_recalculate_snapshot) to also write real counts from now
    on, and existing per-customer history was reset so `calibrating`
    correctly re-triggers instead of comparing a real current count against
    a stale, undercounted baseline (which would otherwise show a fake
    multiplier spike for every customer, not a real volume signal).
    """
    today = date.today()
    window_start = today - timedelta(days=28)

    result = await db.execute(
        select(DailyCaseSnapshot)
        .where(DailyCaseSnapshot.customer_id.is_not(None), DailyCaseSnapshot.snapshot_date >= window_start)
        .order_by(DailyCaseSnapshot.snapshot_date)
    )
    snapshots = result.scalars().all()

    by_customer: dict[int, list] = {}
    for s in snapshots:
        by_customer.setdefault(s.customer_id, []).append(s)

    current_open: dict[int, int] = {}
    names: dict[int, str] = {}
    source = "jira_live"
    if settings.jira_enabled:
        try:
            real_counts = await real_open_counts_by_customer(db)
            for cid, v in real_counts.items():
                current_open[cid] = v["open_count"]
                names[cid] = v["customer_name"]
        except Exception:
            source = "local_fallback"
    else:
        source = "local_fallback"

    if source == "local_fallback":
        open_result = await db.execute(select(Case).where(Case.status != "Closed").options(joinedload(Case.customer)))
        open_cases = open_result.scalars().all()
        for c in open_cases:
            current_open[c.customer_id] = current_open.get(c.customer_id, 0) + 1
            if c.customer:
                names[c.customer_id] = c.customer.name

    leaderboard = []
    for customer_id, current in current_open.items():
        history = by_customer.get(customer_id, [])
        calibrating = len(history) < 7
        baseline = round(statistics.mean(s.open_count for s in history), 1) if history else None
        multiplier = round(current / baseline, 1) if baseline else None
        if calibrating or multiplier is None:
            label = "calibrating"
        elif multiplier >= 1.3:
            label = "loud"
        elif multiplier <= 0.7:
            label = "quiet"
        else:
            label = "steady"

        leaderboard.append({
            "customer_id": customer_id,
            "customer_name": names.get(customer_id, "Unknown"),
            "open_count": current,
            "baseline": baseline,
            "multiplier": multiplier,
            "label": label,
            "calibrating": calibrating,
        })

    leaderboard.sort(key=lambda r: r["open_count"], reverse=True)
    return {"accounts": leaderboard, "source": source}


@router.get("/resolved")
async def resolved_stats(db: AsyncSession = Depends(get_db)):
    """Resolved-ticket signal — deliberately separate from My Desk's operational
    TTR KPI: this is about volume/pace patterns across the whole queue, not
    today's workload.

    Real, live-Jira (real_resolved_stats) rather than the local `cases`
    table — same undercount reason as every other Support Signals endpoint
    fixed this session (local Case.resolved_at only covers tickets a human
    manually mapped to a customer). Falls back to the old local-table query
    only when Jira is disabled or the live fetch fails.
    """
    if settings.jira_enabled:
        try:
            stats = await real_resolved_stats(db, days=90)
            return {**stats, "source": "jira_live"}
        except Exception:
            pass  # degrade to the local-table fallback below

    today = date.today()
    window_start = today - timedelta(days=90)

    result = await db.execute(
        select(Case)
        .where(Case.resolved_at.is_not(None), Case.resolved_at >= window_start)
        .options(joinedload(Case.customer))
    )
    cases = result.scalars().all()

    week_start = today - timedelta(days=7)
    month_start = today - timedelta(days=30)
    resolved_this_week = sum(1 for c in cases if c.resolved_at.date() >= week_start)
    resolved_this_month = sum(1 for c in cases if c.resolved_at.date() >= month_start)

    ttr_hours = [
        (c.resolved_at - c.created_at).total_seconds() / 3600
        for c in cases if c.resolved_at and c.created_at
    ]
    ttr_median_hours = round(statistics.median(ttr_hours), 1) if ttr_hours else None

    by_customer: dict[int, dict] = {}
    for c in cases:
        if not c.customer:
            continue
        entry = by_customer.setdefault(c.customer_id, {"customer_name": c.customer.name, "count": 0})
        entry["count"] += 1

    top_resolved = sorted(by_customer.values(), key=lambda r: r["count"], reverse=True)[:10]

    weekly_trend = []
    for i in range(12, -1, -1):
        w_start = today - timedelta(days=(i + 1) * 7)
        w_end = today - timedelta(days=i * 7)
        count = sum(1 for c in cases if w_start <= c.resolved_at.date() < w_end)
        weekly_trend.append({"week_ending": w_end.isoformat(), "count": count})

    return {
        "window_days": 90,
        "total_resolved_90d": len(cases),
        "resolved_this_week": resolved_this_week,
        "resolved_this_month": resolved_this_month,
        "ttr_median_hours": ttr_median_hours,
        "top_resolved_accounts": top_resolved,
        "weekly_trend": weekly_trend,
        "source": "local_fallback",
    }


@router.get("/exchanges")
async def going_back_and_forth(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Case)
        .where(Case.status != "Closed", Case.comment_count > _EXCHANGE_THRESHOLD)
        .options(joinedload(Case.customer))
        .order_by(Case.comment_count.desc())
    )
    cases = result.scalars().all()
    return {
        "threshold": _EXCHANGE_THRESHOLD,
        "cases": [
            {
                "jira_ref": c.jira_ref,
                "title": c.title,
                "customer_name": c.customer.name if c.customer else None,
                "comment_count": c.comment_count,
            }
            for c in cases
        ],
    }
