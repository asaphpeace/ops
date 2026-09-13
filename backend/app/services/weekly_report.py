"""Orchestrates the weekly ops report — pulls together the ~15 already-
trusted impact/blocking/customer-affected rollups scattered across
releases.py, upgrade_supervision.py, incident_supervision.py,
migration_priority.py, and desk_briefing()'s flags into one coherent,
presentable document for the weekly DevOps priority meeting.

This is assembly, not new computation: almost every number/list here is
produced by a function that already exists and is already relied on
elsewhere in the app — see each section's own comment for its real source.
The one genuinely new piece is the §6 "customers at risk" cross-signal
count, a small aggregation over data every section above already returns.

Every existing router function reused here is called directly as a plain
Python function (passing `db=` explicitly, bypassing its `Depends(get_db)`
default) — the exact same reuse pattern already established in this
codebase by command_center.py::export_scorecard() calling scorecard()
directly.
"""
import asyncio
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.case import Case
from app.models.incident import Incident
from app.models.incident_remediation import IncidentRemediation

from app.routers.command_center import scorecard
from app.routers.desk import desk_briefing
from app.routers.support_signals import aging_buckets
from app.routers.customers import customer_stats
from app.routers.releases import (
    fix_to_relief, version_exposure, engineer_impact, missing_releases,
    defect_dev_status, bug_fix_upgrades_overdue,
)
from app.routers.upgrades import pipeline_summary
from app.routers.migrations import migration_board
from app.routers.incidents import _enrich as _enrich_incident, _enrich_remediation
from app.services.migration_priority import migration_priority
from app.services.upgrade_supervision import (
    overdue_bug_fix_upgrades, enrich_overdue_upgrade,
    superseded_upgrades, unconfirmed_upgrades, enrich_unconfirmed_upgrade,
    pending_upgrades_missing_case, enrich_pending_upgrade_flag,
)
from app.services.incident_supervision import stalled_incidents
from app.services.observation_signals import cross_signal_candidates


def iso_week_bounds(week: str) -> tuple[date, date]:
    """'2026-W37' -> (Monday, Sunday) of that ISO week."""
    year, wk = week.split("-W")
    monday = date.fromisocalendar(int(year), int(wk), 1)
    sunday = date.fromisocalendar(int(year), int(wk), 7)
    return monday, sunday


def current_iso_week() -> str:
    y, w, _ = date.today().isocalendar()
    return f"{y}-W{w:02d}"


def _json_safe(obj):
    """Recursively convert datetime/date values (which leak in from the ~15
    reused rollup functions' ORM-derived dicts) into ISO strings so the
    whole snapshot can be stored in a JSON column — none of those functions
    were written with this in mind, so this is applied once, at the edge,
    rather than patched into every reused function."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


# RAG thresholds — plain code constants, matching this app's established
# convention for business-rule thresholds (TIER_UPGRADE_LIMITS,
# MIN_SELF_SERVICE_VERSION) rather than a DB-editable setting. This is the
# first report ever generated, so these are an honest first pass, not yet
# tuned against real historical variance — revisit once a few real weeks
# exist to calibrate against.
def _rag(value: int, amber_at: int, red_at: int) -> str:
    if value >= red_at:
        return "Red"
    if value >= amber_at:
        return "Amber"
    return "Green"


async def build_weekly_report(db: AsyncSession, week: str) -> dict:
    period_start, period_end = iso_week_bounds(week)

    # Independent, expensive live-Jira-backed calls first, concurrently —
    # same reasoning scorecard() itself already uses for its own internal
    # gather. desk_briefing() and scorecard() both ultimately call
    # team_open_stats() with the same team, so whichever resolves second
    # hits _dedup_fetch's in-memory cache (up to 1h TTL) instead of
    # re-fetching from Jira.
    scorecard_data, briefing_data, aging_data = await asyncio.gather(
        scorecard(window="week", db=db),
        desk_briefing(scope="team", db=db),
        aging_buckets(db=db),
    )

    # Local-DB-only rollups — cheap, safe to run concurrently.
    (
        cust_stats, fix_to_relief_data, version_exposure_data, engineer_impact_data,
        missing_releases_data, defect_dev_status_data, bug_fix_overdue_enriched,
        pipeline_data, migration_board_data, migration_priority_data,
        stalled_incidents_data, cross_signal_data,
        superseded_data, unconfirmed_raw, pending_missing_case_raw,
    ) = await asyncio.gather(
        customer_stats(db=db),
        fix_to_relief(db=db),
        version_exposure(db=db),
        engineer_impact(db=db),
        missing_releases(db=db),
        defect_dev_status(db=db),
        bug_fix_upgrades_overdue(db=db),
        pipeline_summary(db=db),
        migration_board(db=db),
        migration_priority(db),
        stalled_incidents(db),
        cross_signal_candidates(db, scope="team", limit=15),
        superseded_upgrades(db),
        unconfirmed_upgrades(db),
        pending_upgrades_missing_case(db),
    )
    overdue_bug_fix_raw = await overdue_bug_fix_upgrades(db)

    unconfirmed_data = [enrich_unconfirmed_upgrade(u) for u in unconfirmed_raw]
    pending_missing_case_data = [enrich_pending_upgrade_flag(c) for c in pending_missing_case_raw]
    overdue_bug_fix_data = [enrich_overdue_upgrade(u) for u in overdue_bug_fix_raw]

    # Blocked Support cases — small, genuinely new query. The field already
    # exists on Case (blocked/blocked_reason), it's just never been rolled
    # into a report before.
    blocked_cases_result = await db.execute(
        select(Case).where(Case.blocked == True).options(joinedload(Case.customer))  # noqa: E712
    )
    blocked_cases = [
        {
            "jira_ref": c.jira_ref, "title": c.title, "blocked_reason": c.blocked_reason,
            "customer_id": c.customer_id,
            "customer_name": c.customer.name if c.customer else c.jira_customer_name,
            "customer_tier": c.customer.tier if c.customer else None,
        }
        for c in blocked_cases_result.scalars().all()
    ]

    # Open, product-source incidents + their per-customer remediation
    # rollup — reuses the exact same _enrich/_enrich_remediation helpers
    # GET /incidents/{id} already uses, just applied to every open incident
    # at once instead of one at a time.
    open_incidents_result = await db.execute(
        select(Incident).where(Incident.status == "Open").order_by(Incident.severity)
    )
    open_incidents = open_incidents_result.scalars().all()
    incident_rows = []
    if open_incidents:
        remediations_result = await db.execute(
            select(IncidentRemediation)
            .where(IncidentRemediation.incident_id.in_([i.id for i in open_incidents]))
            .options(joinedload(IncidentRemediation.customer), joinedload(IncidentRemediation.upgrade))
        )
        remediations_by_incident: dict[int, list[IncidentRemediation]] = {}
        for r in remediations_result.scalars().all():
            remediations_by_incident.setdefault(r.incident_id, []).append(r)
        for inc in open_incidents:
            out = _enrich_incident(inc)
            out["remediations"] = [_enrich_remediation(r) for r in remediations_by_incident.get(inc.id, [])]
            incident_rows.append(out)

    # §6 — cross-cutting "customers at risk": a real count of how many of
    # the above signals currently touch each customer. The one genuinely
    # NEW piece of computation in this whole report — everything it reads
    # from is already fetched above, this just re-groups it per customer.
    signal_counts: dict[int, dict] = {}

    def _bump(customer_id: int | None, name: str | None, tier: str | None, signal: str) -> None:
        if not customer_id:
            return
        entry = signal_counts.setdefault(
            customer_id, {"customer_id": customer_id, "customer_name": name, "customer_tier": tier, "signals": []},
        )
        entry["signals"].append(signal)

    for c in blocked_cases:
        _bump(c["customer_id"], c["customer_name"], c["customer_tier"], f"Blocked case {c['jira_ref']}")
    for u in briefing_data["flags"]["blocked_upgrades"]:
        _bump(u["customer_id"], u["customer_name"], None, f"Blocked upgrade {u['jira_ref']}")
    for m in briefing_data["flags"]["stalled_migrations"]:
        _bump(m["customer_id"], m["customer_name"], None, "Stalled migration")
    for inc in incident_rows:
        for r in inc["remediations"]:
            if r["derived_status"] == "In progress":
                _bump(r["customer_id"], r["customer_name"], r["customer_tier"], f"Open incident: {inc['title']}")
    for item in version_exposure_data:
        for cust in item["silently_exposed_customers"]:
            _bump(cust["id"], cust["name"], cust["tier"], f"Exposed to unreported defect {item['vms_ref']}")

    customers_at_risk = [e for e in signal_counts.values() if len(e["signals"]) >= 2]
    customers_at_risk.sort(key=lambda e: -len(e["signals"]))

    # §0 — RAG grid. Reuses scalar counts already computed above rather
    # than re-deriving anything.
    rag = {
        "Support": _rag(scorecard_data["support"]["sla_breach_count"], amber_at=5, red_at=15),
        "Bugs": _rag(sum(len(i["silently_exposed_customers"]) for i in version_exposure_data), amber_at=3, red_at=10),
        "Upgrades": _rag(pipeline_data["blocked"], amber_at=1, red_at=3),
        "Migrations": _rag(briefing_data["flags"]["stalled_migration_count"], amber_at=1, red_at=3),
        "Incidents": _rag(len(stalled_incidents_data), amber_at=1, red_at=2),
    }

    bluf = (
        f"{scorecard_data['support']['sla_breach_count']} SLA breaches, "
        f"{pipeline_data['blocked']} blocked upgrades, "
        f"{briefing_data['flags']['stalled_migration_count']} stalled migrations, "
        f"{len(open_incidents)} open incidents — "
        f"{len(customers_at_risk)} customers hit by 2+ real signals this week."
    )

    return _json_safe({
        "week": week,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "bluf": bluf,
        "rag": rag,
        "support": {
            "scorecard": scorecard_data["support"],
            "aging": aging_data,
            "blocked_cases": blocked_cases,
        },
        "bugs": {
            "fix_to_relief": fix_to_relief_data,
            "version_exposure": version_exposure_data,
            "engineer_impact": engineer_impact_data,
            "missing_releases": missing_releases_data,
            "defect_dev_status": defect_dev_status_data,
            "bug_fix_upgrades_overdue": bug_fix_overdue_enriched,
        },
        "upgrades": {
            "pipeline": pipeline_data,
            "superseded": superseded_data,
            "unconfirmed": unconfirmed_data,
            "pending_missing_case": pending_missing_case_data,
            "overdue_bug_fix": overdue_bug_fix_data,
        },
        "migrations": {
            "board": migration_board_data,
            "priority": migration_priority_data,
        },
        "incidents": {
            "open": incident_rows,
            "stalled": stalled_incidents_data,
        },
        "customers_at_risk": customers_at_risk,
        "customer_arr_stats": cust_stats,
        "cross_signal": cross_signal_data,
    })
