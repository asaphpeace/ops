"""
Command Center — a personal work-measurement view. Pure observability: no
scheduling actions live here (those stay in Operations); this pulls
completions/schedule/briefing data together across all 4 coordination
workflows (Upgrades/Migrations/SSO/Cancellations) plus curated support KPIs.

Shaped directly with the user across several rounds of discussion — see the
plan file for the full decision trail (why "this month only" became a
week/month/quarter toggle, why Cancellations stays a due-date list instead
of a forced slot, why "Severity 1" became "High priority" as the practical
proxy, etc).
"""
import asyncio
import csv
import io
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import settings
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.cancellation import Cancellation
from app.models.case import Case
from app.models.customer import Customer
from app.models.migration_project import MigrationProject
from app.models.sso_onboarding import SSOOnboarding
from app.models.upgrade import Upgrade
from app.routers.cancellations import _overdue
from app.routers.desk import SUPPORT_TEAM, desk_summary
from app.services.daily_ops import daily_ops_stats
from app.services.jira import team_created_stats, team_open_stats, team_resolved_stats
from app.services.lanes import waiting_on
from app.services.time_windows import VALID_WINDOWS, window_start
import statistics
from datetime import timezone

# Same 30/90/365 thresholds as support_signals.py::aging_buckets, collapsed
# to the 3 buckets that actually matter for "what's aging badly" at a glance
# (0-7/8-30 are healthy — no need to break those out here too).
_AGED_BUCKETS = [
    ("31-90 days", 31, 90),
    ("91-365 days", 91, 365),
    ("over 1 year", 366, None),
]

router = APIRouter(prefix="/command-center", tags=["command-center"])

# Curated, not exhaustive — the general audit trail (case.status_changed,
# bug.status_changed, alert_fired, case.escalated) is already surfaced on
# My Desk's own Activity Feed. This is "what's new and worth knowing," not
# a duplicate of that.
_BRIEFING_ACTIONS = (
    "upgrade.auto_started", "upgrade.created",
    "migration.created", "migration.initiated",
    "sso.auto_started",
    "cancellation.requested",
    "customer.hypercare_set",
    "case.high_priority",
)


def _check_window(window: str) -> None:
    if window not in VALID_WINDOWS:
        raise HTTPException(status_code=422, detail=f"window must be one of {VALID_WINDOWS}")


@router.get("/scorecard")
async def scorecard(window: str = "month", db: AsyncSession = Depends(get_db)):
    _check_window(window)
    start = window_start(window)

    upgrades_completed = (await db.execute(
        select(Upgrade).where(Upgrade.stage == "Verified Done", Upgrade.verified_at >= start)
    )).scalars().all()
    migrations_completed = (await db.execute(
        select(MigrationProject).where(MigrationProject.completed_at.is_not(None), MigrationProject.completed_at >= start)
    )).scalars().all()
    sso_live = (await db.execute(
        select(SSOOnboarding).where(SSOOnboarding.stage == "SSO Live", SSOOnboarding.switchover_at.is_not(None), SSOOnboarding.switchover_at >= start)
    )).scalars().all()
    cancellations_done = (await db.execute(
        select(Cancellation).where(Cancellation.stage == "Decommissioned", Cancellation.decommissioned_at.is_not(None), Cancellation.decommissioned_at >= start)
    )).scalars().all()

    # Local fallback base — used only when Jira is disabled/unreachable
    # below (joinedload(customer) needed for that fallback path's case_mix).
    open_cases = (await db.execute(
        select(Case).where(Case.status != "Closed").options(joinedload(Case.customer))
    )).scalars().all()

    # Days-in-window, computed from the real calendar window_start rather
    # than hardcoded per-window numbers — correctly handles month/year's
    # calendar-based (not fixed-length) semantics. Needed up front now (not
    # after open_stats, as before) since it feeds every fetch in the gather
    # below.
    days_in_window = max(1, (date.today() - start.date()).days)
    if window in ("month", "year"):
        resolved_created_kwargs: dict = {"start": start.date(), "end": date.today() + timedelta(days=1)}
    else:
        resolved_created_kwargs = {"days": days_in_window}

    # Four independent live-Jira fetches, run concurrently instead of one
    # after another. Confirmed live this mattered a lot: team_open_stats
    # (SLA/Case Mix/Aged Cases), the resolved/created pair (TTFR/TTR/Cases
    # Logged), and daily_ops_stats (Assigned/Resolved/Opened/Replies/
    # Comments + the fresh/backlog split) don't depend on each other's
    # results at all, but ran sequentially before — stacking to 60s+ once
    # daily_ops_stats' own cost grew (the fresh/backlog split added a
    # per-resolved-ticket comment fetch). return_exceptions keeps one
    # fetch's failure from taking down the other three, matching the
    # per-call try/except degrade-gracefully behavior this endpoint already
    # had before the gather.
    open_stats = resolved_stats = created_stats = daily_ops = None
    if settings.jira_enabled:
        results = await asyncio.gather(
            team_open_stats(db, SUPPORT_TEAM),
            team_resolved_stats(db, SUPPORT_TEAM, **resolved_created_kwargs),
            team_created_stats(SUPPORT_TEAM, **resolved_created_kwargs),
            daily_ops_stats(db, SUPPORT_TEAM, days_in_window),
            return_exceptions=True,
        )
        open_stats, resolved_stats, created_stats, daily_ops = (
            r if not isinstance(r, Exception) else None for r in results
        )

    # Live-Jira open-ticket detail — powers SLA Breaching, Case Mix, and
    # Aged Cases below. All three used to be computed from the local
    # `cases` table, which badly undercounts real volume (79 locally vs.
    # 569 real — confirmed live) and specific statuses even worse (2 of 151
    # real "Defect / Enhancement submitted" tickets were locally mapped,
    # since most tickets are never manually linked to a customer record
    # until someone actively works them).
    live_tickets = (
        [t for cases in open_stats["by_status"].values() for t in cases] if open_stats else None
    )

    # SLA breach count — same definition as desk_briefing()'s sla_flagged,
    # a real-time gauge (not window-summed, there's only ever "currently
    # breaching" for open tickets). `sla_days` is effectively dead for real
    # (non-seed) data — confirmed live, only 2 of 79 local cases ever have
    # it set — so the live path only needs the native Jira TTFR-breach flag.
    if live_tickets is not None:
        sla_breach_count = sum(1 for t in live_tickets if t["ttfr_breached"])
        sla_breach_tickets = [t for t in live_tickets if t["ttfr_breached"]]
    else:
        sla_breaching_cases = [c for c in open_cases if c.ttfr_breached or (c.sla_days and c.days_open > c.sla_days)]
        sla_breach_count = len(sla_breaching_cases)
        sla_breach_tickets = [
            {
                "jira_ref": c.jira_ref, "title": c.title, "assignee_name": c.assigned_to,
                "customer_name": c.customer.name if c.customer else None, "days_open": c.days_open,
            }
            for c in sla_breaching_cases
        ]

    # TTFR/TTR median — from the resolved/created gather above. Resolved/
    # Assigned/Replies/Comments all come from the ONE shared daily_ops_stats
    # call instead — this used to also call team_resolved_stats a second
    # time just for total_resolved, which duplicated the same underlying
    # Jira data daily_ops_stats already fetches.
    ttfr_median_hours = resolved_stats["total_ttfr_median_hours"] if resolved_stats else None
    # Same fix as TTFR above: this was previously only available via
    # desk_summary()'s hardcoded rolling-30-day figure, silently ignoring
    # the page's own window toggle. Already computed by the same
    # team_resolved_stats() call above — just wasn't being returned.
    ttr_median_hours = resolved_stats["total_ttr_median_hours"] if resolved_stats else None

    # Cases Logged — how many real tickets were CREATED in this window,
    # regardless of current status. Genuinely missing before this: neither
    # daily_ops_stats' "assigned" (an assignment-change event, not a new
    # ticket) nor anything else in this endpoint answered "how many cases
    # came in" — confirmed via grep, no created_count anywhere in this file.
    logged_count = created_stats["total_created"] if created_stats else None
    logged_by_engineer = created_stats["by_engineer"] if created_stats else None
    # Real per-ticket detail behind the above — same source (team_created_
    # stats), flattened across the named team for the tile's own drill-down.
    # Named-team scope only (not logged_count's unfiltered project-wide
    # total) — same "roster, not everyone" boundary as desk_team()'s own
    # team-total ticket lists.
    logged_tickets = (
        [t for n in SUPPORT_TEAM for t in created_stats["tickets_by_engineer"][n]] if created_stats else []
    )

    # Real per-ticket detail behind the "Resolved" tile's window total —
    # daily_ops's per-day resolved_tickets already carry it (used by the
    # Closed Tickets panel's per-day buckets below); flattening across the
    # whole window here is the same data, just concatenated once for the
    # top-tile's own drill-down instead of only per-day.
    resolved_tickets_window = (
        [t for day in daily_ops["series"] for t in day["resolved_tickets"]] if daily_ops else []
    )

    def _daily_ops_total(metric: str) -> int | None:
        if not daily_ops:
            return None
        return sum(daily_ops["totals"][n][metric] for n in SUPPORT_TEAM)

    resolved_count = _daily_ops_total("resolved")
    fresh_resolved_count = _daily_ops_total("fresh_resolved")
    assigned_count = _daily_ops_total("assigned")
    fresh_assigned_count = _daily_ops_total("fresh_assigned")
    replies_count = _daily_ops_total("replies")
    comments_count = _daily_ops_total("comments")

    # Real, live-Jira daily closed series for the "Closed Tickets" panel —
    # reuses the same daily_ops_stats() call above (no new fetch). Was
    # previously sourced from DailyCaseSnapshot.closed_count, which (unlike
    # that table's open_count) is computed from the local `cases` table only
    # and structurally undercounts real closures the same way open_count
    # used to before it was pointed at live Jira — confirmed live: 6 closed
    # in 7 days locally vs. real team resolution volume in the dozens.
    # tickets carries the real per-ticket detail behind that day's count
    # (already SUPPORT_TEAM-filtered by team_daily_resolved itself) — powers
    # the drillable "click a bucket, see what's in it" behavior on the panel,
    # same pattern as Case Mix by Status.
    daily_closed_series = (
        [
            {
                "date": day["date"],
                "closed": sum(day["engineers"][n]["resolved"] for n in SUPPORT_TEAM),
                "fresh_closed": sum(day["engineers"][n]["fresh_resolved"] for n in SUPPORT_TEAM),
                "tickets": day["resolved_tickets"],
            }
            for day in daily_ops["series"]
        ]
        if daily_ops else []
    )

    # Same shape/reasoning as daily_closed_series above, for the "Opened
    # Tickets" panel — real, live-Jira daily created counts (team_daily_
    # created, wired into daily_ops_stats() as its "opened" dimension), no
    # new fetch. Sticks to the same SUPPORT_TEAM filter as every other
    # number on this page rather than the unfiltered project-wide total
    # team_created_stats() also returns.
    daily_opened_series = (
        [
            {
                "date": day["date"],
                "opened": sum(day["engineers"][n]["opened"] for n in SUPPORT_TEAM),
                "tickets": day["opened_tickets"],
            }
            for day in daily_ops["series"]
        ]
        if daily_ops else []
    )

    # Per-engineer breakdown of the same daily_ops_stats call above — this
    # data was already being computed and then discarded down to the team
    # sum; surfacing it per-name is what actually lets the frontend show
    # "assigned to you" instead of only a team-wide total.
    by_engineer = {
        n: (
            {
                "assigned": daily_ops["totals"][n]["assigned"],
                "fresh_assigned": daily_ops["totals"][n]["fresh_assigned"],
                "resolved": daily_ops["totals"][n]["resolved"],
                "fresh_resolved": daily_ops["totals"][n]["fresh_resolved"],
                "replies": daily_ops["totals"][n]["replies"],
                "comments": daily_ops["totals"][n]["comments"],
                "logged": logged_by_engineer[n]["created"] if logged_by_engineer else None,
            }
            if daily_ops else (
                {"assigned": None, "fresh_assigned": None, "resolved": None, "fresh_resolved": None, "replies": None, "comments": None,
                 "logged": logged_by_engineer[n]["created"] if logged_by_engineer else None}
                if logged_by_engineer else None
            )
        )
        for n in SUPPORT_TEAM
    }

    # Time-to-first-move, window-scoped — mirrors desk_summary()'s own
    # computation (status_changed_at - created_at, median) but bounded by
    # THIS endpoint's own `start` instead of desk_summary()'s hardcoded
    # rolling-30-day window, so it actually respects the page's toggle
    # instead of silently ignoring it.
    move_result = await db.execute(
        select(Case).where(Case.status_changed_at.is_not(None), Case.created_at >= start)
    )
    move_cases = move_result.scalars().all()
    move_hours = [
        (c.status_changed_at - c.created_at).total_seconds() / 3600
        for c in move_cases if c.status_changed_at and c.created_at
    ]
    median_time_to_first_move_hours = round(statistics.median(move_hours), 1) if move_hours else None

    # Open-load vs baseline is a point-in-time gauge (right now vs your
    # last-28-days baseline), not something that changes per reporting
    # window — reuses desk_summary()'s exact computation rather than
    # duplicating the DailyCaseSnapshot baseline logic.
    summary = await desk_summary(db)

    # Waiting-on-me time — mirrors alerts.py's days_waiting computation
    # (now - status_changed_at, falling back to created_at when a case has
    # never moved), applied to cases currently sitting in the "me" lane
    # rather than "Awaiting Customer" — a median instead of a per-case alert.
    now = datetime.now(timezone.utc)
    mine = [c for c in open_cases if waiting_on(c) == "me"]
    waiting_hours = []
    for c in mine:
        anchor = c.status_changed_at or c.created_at
        if anchor:
            waiting_hours.append((now - anchor).total_seconds() / 3600)
    waiting_on_me_median_hours = round(statistics.median(waiting_hours), 1) if waiting_hours else None

    # Case Mix by Status — real, uncollapsed Jira status string. Each bucket
    # carries the real tickets behind its count/percentage, oldest-first,
    # plus `your_count` (how many are assigned to you specifically) — added
    # after live verification found a real "14 defects" complaint traced to
    # exactly this: the bar showed the bucket's full team-wide total (151)
    # with no way to see how many were yours without manually scanning the
    # expanded list for your name.
    case_mix: list[dict] = []
    if live_tickets is not None:
        case_mix = [
            {
                "status": status,
                "count": len(cases),
                "your_count": sum(1 for c in cases if c["assignee_name"] == SUPPORT_TEAM[0]),
                "cases": sorted(cases, key=lambda c: -(c["days_open"] or 0)),
            }
            for status, cases in sorted(open_stats["by_status"].items(), key=lambda kv: -len(kv[1]))
        ]
    if not case_mix:
        # Local fallback only — Jira disabled/unreachable.
        mix: dict[str, list[Case]] = {}
        for c in open_cases:
            key = c.raw_status or c.status
            mix.setdefault(key, []).append(c)
        case_mix = [
            {
                "status": k,
                "count": len(cases),
                "your_count": sum(1 for c in cases if c.assigned_to == SUPPORT_TEAM[0]),
                "cases": [
                    {
                        "jira_ref": c.jira_ref,
                        "title": c.title,
                        "assignee_name": c.assigned_to,
                        "customer_name": c.customer.name if c.customer else None,
                        "days_open": c.days_open,
                    }
                    for c in sorted(cases, key=lambda c: -c.days_open)
                ],
            }
            for k, cases in sorted(mix.items(), key=lambda kv: -len(kv[1]))
        ]

    # Aged Cases — same 30/90/365 thresholds as support_signals.py's aging
    # view, collapsed to the 3 buckets that actually need attention, with a
    # few real example refs per bucket so it's actionable, not just a count.
    aged_cases = []
    if live_tickets is not None:
        for label, lo, hi in _AGED_BUCKETS:
            rows = [t for t in live_tickets if t["days_open"] is not None and lo <= t["days_open"] and (hi is None or t["days_open"] <= hi)]
            aged_cases.append({
                "label": label,
                "count": len(rows),
                "example_refs": [t["jira_ref"] for t in sorted(rows, key=lambda t: -t["days_open"])[:3]],
            })
    else:
        for label, lo, hi in _AGED_BUCKETS:
            rows = [c for c in open_cases if c.days_open >= lo and (hi is None or c.days_open <= hi)]
            aged_cases.append({
                "label": label,
                "count": len(rows),
                "example_refs": [c.jira_ref for c in sorted(rows, key=lambda c: -c.days_open)[:3]],
            })

    return {
        "window": window,
        "upgrades_completed": len(upgrades_completed),
        "migrations_completed": len(migrations_completed),
        "sso_live": len(sso_live),
        "cancellations_decommissioned": len(cancellations_done),
        "support": {
            "resolved_count": resolved_count,
            "fresh_resolved_count": fresh_resolved_count,
            "assigned_count": assigned_count,
            "fresh_assigned_count": fresh_assigned_count,
            "replies_count": replies_count,
            "comments_count": comments_count,
            "logged_count": logged_count,
            "logged_tickets": logged_tickets,
            "resolved_tickets": resolved_tickets_window,
            "sla_breach_tickets": sla_breach_tickets,
            "by_engineer": by_engineer,
            "daily_closed_series": daily_closed_series,
            "daily_opened_series": daily_opened_series,
            "ttfr_median_hours": ttfr_median_hours,
            "ttr_median_hours": ttr_median_hours,
            "median_time_to_first_move_hours": median_time_to_first_move_hours,
            "sla_breach_count": sla_breach_count,
            "open_load": summary["open_load"],
            "open_load_baseline": summary["open_load_baseline"],
            "open_load_vs_baseline_pct": summary["open_load_vs_baseline_pct"],
            "waiting_on_me_median_hours": waiting_on_me_median_hours,
            "case_mix": case_mix,
            "aged_cases": aged_cases,
        },
    }


@router.get("/export")
async def export_scorecard(window: str = "month", db: AsyncSession = Depends(get_db)):
    """CSV export of the current window's scorecard — borrowed from the
    reference-dashboard critique's "export the current view" idea. Scoped to
    CSV only, deliberately: a real PDF report would need a new dependency
    (reportlab/weasyprint, neither present in this app today) and real layout
    work, which is a separate, bigger feature — this reuses scorecard()'s
    existing data wholesale rather than re-querying anything.
    """
    _check_window(window)
    data = await scorecard(window, db)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["metric", "value"])
    writer.writerow(["window", data["window"]])
    writer.writerow(["upgrades_completed", data["upgrades_completed"]])
    writer.writerow(["migrations_completed", data["migrations_completed"]])
    writer.writerow(["sso_live", data["sso_live"]])
    writer.writerow(["cancellations_decommissioned", data["cancellations_decommissioned"]])
    support = data["support"]
    for key in (
        "assigned_count", "fresh_assigned_count", "resolved_count", "fresh_resolved_count", "replies_count", "comments_count", "logged_count",
        "ttfr_median_hours", "sla_breach_count", "open_load",
        "open_load_baseline", "open_load_vs_baseline_pct", "waiting_on_me_median_hours",
    ):
        writer.writerow([key, support.get(key)])
    writer.writerow([])
    writer.writerow(["case_mix_status", "count"])
    for row in support["case_mix"]:
        writer.writerow([row["status"], row["count"]])
    writer.writerow([])
    writer.writerow(["aged_case_bucket", "count", "example_refs"])
    for row in support["aged_cases"]:
        writer.writerow([row["label"], row["count"], ";".join(row["example_refs"])])

    filename = f"command-center-{window}-{date.today().isoformat()}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/schedule")
async def schedule(window: str = "month", db: AsyncSession = Depends(get_db)):
    _check_window(window)
    start = window_start(window)

    # "Upcoming" is inherently prospective, unlike every other metric on this
    # page (which is retrospective and correctly bounded by `start`, the
    # backward-looking window). Reusing `start` here as the ONLY bound meant
    # this panel had no upper bound at "now" at all — a slot from earlier
    # this month showed up as "upcoming" days after it happened. Real fix:
    # never below now, and look FORWARD by the same span the window
    # represents (e.g. "week" -> next ~7 days) instead of back to `start`.
    now = datetime.utcnow()
    lookahead_end = now + (now - start)

    # A short lookback (not just >= now) so a slot that's already passed
    # without real confirmation doesn't just silently vanish from
    # "Upcoming" — confirmed live this was exactly how a real Rosco upgrade
    # (DSD-31779) slipped by unnoticed: scheduled, never confirmed by
    # either DevOps or the customer, and gone from this view the moment its
    # time passed. Anything within the lookback still shows if either
    # confirmation is missing; a fully-confirmed past slot still ages out
    # normally (nothing left to catch there).
    unconfirmed_lookback = now - timedelta(days=3)
    upgrades = (await db.execute(
        select(Upgrade).where(
            # Confirmed live: a Cancelled row with a real scheduled_at (set
            # before it was cancelled) matched every other condition here —
            # unconfirmed + within the lookback — and kept showing on
            # "Upcoming Schedule" indefinitely (Peak People AS/DSD-31933).
            # Every other Upgrade query in this app already excludes these
            # two terminal stages; this one query was the one place that
            # never did.
            Upgrade.stage.notin_(("Verified Done", "Cancelled")),
            Upgrade.scheduled_at.is_not(None),
            Upgrade.scheduled_at <= lookahead_end,
            (Upgrade.scheduled_at >= now) | (
                (Upgrade.scheduled_at >= unconfirmed_lookback)
                & ((Upgrade.devops_confirmed_at.is_(None)) | (Upgrade.customer_confirmed_at.is_(None)))
            ),
        ).options(joinedload(Upgrade.customer))
    )).scalars().all()
    migrations = (await db.execute(
        select(MigrationProject).where(
            MigrationProject.downtime_agreed_at.is_not(None),
            MigrationProject.downtime_agreed_at >= now, MigrationProject.downtime_agreed_at <= lookahead_end,
        ).options(joinedload(MigrationProject.customer))
    )).scalars().all()
    ssos = (await db.execute(
        select(SSOOnboarding).where(
            SSOOnboarding.switchover_at.is_not(None),
            SSOOnboarding.switchover_at >= now, SSOOnboarding.switchover_at <= lookahead_end,
        ).options(joinedload(SSOOnboarding.customer))
    )).scalars().all()

    slots = [
        {
            "type": "Upgrade", "customer_name": u.customer.name if u.customer else None,
            "customer_tier": u.customer.tier if u.customer else None, "customer_id": u.customer_id,
            "scheduled_at": u.scheduled_at, "duration_minutes": u.duration_minutes,
            "detail": f"{u.from_version or '—'} → {u.to_version}", "id": u.id,
            "stage": u.stage,
            "devops_confirmed": u.devops_confirmed_at is not None,
            "customer_confirmed": u.customer_confirmed_at is not None,
        }
        for u in upgrades
    ] + [
        {
            "type": "Migration", "customer_name": m.customer.name if m.customer else None,
            "customer_tier": m.customer.tier if m.customer else None, "customer_id": m.customer_id,
            "scheduled_at": m.downtime_agreed_at, "duration_minutes": m.downtime_duration_mins,
            "detail": m.stage, "id": m.id,
        }
        for m in migrations
    ] + [
        {
            "type": "SSO", "customer_name": s.customer.name if s.customer else None,
            "customer_tier": s.customer.tier if s.customer else None, "customer_id": s.customer_id,
            "scheduled_at": s.switchover_at, "duration_minutes": s.switchover_duration_mins,
            "detail": s.stage, "id": s.id,
        }
        for s in ssos
    ]
    slots.sort(key=lambda r: r["scheduled_at"])

    cancellations = (await db.execute(
        select(Cancellation)
        .where(Cancellation.stage != "Decommissioned", Cancellation.effective_date >= start.date(), Cancellation.effective_date <= date.today() + timedelta(days=90))
        .options(joinedload(Cancellation.customer))
    )).scalars().all()
    due = [
        {
            "customer_name": c.customer.name if c.customer else None,
            "customer_tier": c.customer.tier if c.customer else None, "customer_id": c.customer_id,
            "effective_date": c.effective_date, "overdue": _overdue(c), "stage": c.stage, "id": c.id,
        }
        for c in cancellations
    ]
    due.sort(key=lambda r: r["effective_date"])

    # Informational only — the user's own known real DevOps capacity
    # constraint (~6 slots/week). No blocking, no overbook warning, just
    # visibility before committing to a date, per direct decision.
    week_start = now - timedelta(days=now.weekday())
    week_start = datetime(week_start.year, week_start.month, week_start.day)
    week_end = week_start + timedelta(days=7)
    slots_this_week = (await db.execute(
        select(Upgrade).where(
            Upgrade.scheduled_at.is_not(None),
            Upgrade.scheduled_at >= week_start, Upgrade.scheduled_at < week_end,
            Upgrade.stage != "Cancelled",
        )
    )).scalars().all()

    return {
        "window": window, "slots": slots, "cancellations_due": due,
        "devops_slots_this_week": len(slots_this_week),
        "devops_slots_per_week": settings.devops_slots_per_week,
    }


@router.get("/briefing")
async def briefing(window: str = "month", db: AsyncSession = Depends(get_db)):
    _check_window(window)
    start = window_start(window)

    events = (await db.execute(
        select(AuditLog)
        .where(AuditLog.action.in_(_BRIEFING_ACTIONS), AuditLog.created_at >= start)
        .order_by(AuditLog.created_at.desc())
        .limit(50)
    )).scalars().all()

    customer_ids = {int(e.target_id) for e in events if e.target_type == "customer" and e.target_id and e.target_id.isdigit()}
    customers_by_id = {
        c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars().all()
    } if customer_ids else {}

    return {
        "window": window,
        "events": [
            {
                "action": e.action,
                "target_type": e.target_type,
                "target_id": e.target_id,
                "customer_name": customers_by_id[int(e.target_id)].name
                if e.target_type == "customer" and e.target_id and e.target_id.isdigit() and int(e.target_id) in customers_by_id
                else None,
                "detail": e.detail,
                "created_at": e.created_at,
            }
            for e in events
        ],
    }
