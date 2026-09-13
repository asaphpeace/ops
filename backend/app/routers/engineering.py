"""
Engineering — the real technical state of the fleet: fleet version
composition, per-customer environment inventory (Dataloy tenant data +
matched real AWS resources), and a cross-linked summary of the
bug/defect/upgrade intelligence Release Intelligence already computes.

This router is deliberately thin where Release Intelligence already owns
the logic — every reused function below is called directly as a plain
Python function (db= passed explicitly, bypassing its own
Depends(get_db) default), the same reuse pattern already established by
command_center.py::export_scorecard() and weekly_report.py. None of those
functions are modified by this file; Release Intelligence's own page is
provably unaffected.

The one genuinely new view here is the Environment Matrix — nothing today
shows "every real VMS customer, every environment, side by side" in one
flat grid.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import AsyncSessionLocal, get_db
from app.models.audit_log import AuditLog
from app.models.aws_resource import AwsResource, AwsResourceMetricSnapshot
from app.models.case import Case
from app.models.customer import Customer
from app.models.customer_tenant_info import CustomerTenantInfo
from app.models.engineering_snapshot import EngineeringDailySnapshot
from app.models.incident import Incident
from app.models.incident_remediation import IncidentRemediation
from app.models.log_entry import LogEntry
from app.models.release import Release
from app.models.runbook import Runbook
from app.models.upgrade import Upgrade
from app.models.vms_bug import VmsBug
from app.services.bug_linkage import cases_by_bug_ref

from app.routers.releases import (
    version_exposure, engineer_impact, missing_releases,
    customers_below_latest, version_distribution,
    bug_fix_upgrades_overdue, pending_upgrade_queue,
    _version_tuple,
)
from app.services.migration_priority import migration_priority
from app.services.aws_import import parse_ec2, parse_rds, parse_cloudwatch, build_match_maps, match_candidate
from app.services.log_import import parse_cloudwatch_log_events, parse_cloudtrail_events
from app.services.cert_scan import (
    CERT_CRITICAL_DAYS, CERT_WARN_DAYS, cert_status, days_until_expiry, is_scan_running, _resolve_hostname,
)

router = APIRouter(prefix="/engineering", tags=["engineering"])
logger = logging.getLogger(__name__)

_ENVIRONMENTS = ["PROD", "TEST", "DEV"]
_LOG_TYPES = ["application", "rds", "cloudtrail", "vpc_flow"]

# A search with no query still needs a bound — this isn't a real log
# platform's index, it's Postgres reading a bounded, periodically-imported
# table. Matches the same "cap it, don't pretend infinite scale" instinct
# already used elsewhere (VMS Sandbox's 2000-object warning).
_MAX_LOG_RESULTS = 500

# Fixed threshold for "under load" — a plain code constant, matching this
# app's established convention for business-rule thresholds
# (TIER_UPGRADE_LIMITS, MIN_SELF_SERVICE_VERSION) rather than a
# DB-editable setting.
_CPU_UNDER_LOAD_PCT = 85.0

# Risk-label buckets over migration_priority()'s existing real
# priority_score (tier + infra + incident-severity + defect weights,
# observed real range ~2-14) — a plain code-constant threshold, same
# convention as _CPU_UNDER_LOAD_PCT/_HIGH_RISK_SCORE. Deliberately reuses
# the one real, already-shipped score rather than inventing a second
# scoring formula for the Matrix's Risk column.
_RISK_LABEL_BUCKETS = [(12, "Critical"), (8, "High"), (4, "Medium"), (0, "Low")]


def _risk_label(score: int) -> str:
    for cutoff, label in _RISK_LABEL_BUCKETS:
        if score >= cutoff:
            return label
    return "Low"


# Reuses version_distribution()'s exact real minor-version-range
# boundaries (8.30+/8.28-29/8.25-27/8.23-24/8.17-22/<8.17) translated to
# status labels, rather than a second set of thresholds — the "Current"
# label additionally requires an exact match to the real latest version,
# not just membership in the top band.
_RELEASE_STATUS_BUCKETS = [
    (30, "Supported"), (28, "Supported"), (25, "Supported"),
    (23, "Ageing"), (17, "Legacy"), (0, "End of life"),
]


def _release_status(version: str | None, latest_version: str | None) -> str | None:
    if not version:
        return None
    v = _version_tuple(version)
    if not v or len(v) < 2:
        return "Unknown"
    if latest_version and version == latest_version:
        return "Current"
    for cutoff, label in _RELEASE_STATUS_BUCKETS:
        if v[1] >= cutoff:
            return label
    return "End of life"


def _hosting_model(resource: AwsResource | None, aws_environment_fallback: str | None = None) -> str | None:
    """A real, small classification heuristic — no explicit
    "containerized" field exists on an AwsResource import today. Checks
    the real resource_id/name for an ECS-style path first (the "ecs/..."
    naming already observed on real confirmed resources this session);
    otherwise falls back to the same Old-AWS-is-legacy-manual-VM
    convention already established by the earlier Old-AWS-migration
    effort — real, not guessed, but coarse until real container-platform
    tags are imported."""
    if resource is None:
        return None
    name_or_id = (resource.name or resource.resource_id or "").lower()
    if "ecs" in name_or_id or "docker" in name_or_id:
        return "Docker / ECS"
    if resource.aws_environment == "Old":
        return "Legacy VM"
    return "EC2" if resource.resource_type == "EC2" else "RDS"


# Real Postgres major-version EOL dates (community EOL schedule) — a plain
# code constant, same "checkable vendor fact, not invented" convention as
# TIER_UPGRADE_LIMITS elsewhere. Anything outside this table renders
# "Unknown" rather than guessing a lifecycle state.
_POSTGRES_EOL = {
    "11": ("2023-11-09", "End of life"),
    "12": ("2024-11-14", "End of life"),
    "13": ("2025-11-13", "End of life"),
    "14": ("2026-11-12", "Supported"),
    "15": ("2027-11-11", "Supported"),
    "16": ("2028-11-09", "Supported"),
    "17": ("2029-11-08", "Supported"),
}

_HOSTING_COLORS = {
    "Docker / ECS": "var(--accent)",
    "EC2": "var(--green)",
    "RDS": "var(--accent)",
    "Legacy VM": "var(--amber)",
}


def _infra_accounts(all_resources: list[AwsResource]) -> list[dict]:
    """One card per real AWS account (Old/New) — the two environments this
    app already tracks via Customer.infra. When an account has zero
    imported resources (today's real, honest state for both), the card
    shows the exact copy-pasteable export command rather than a bare
    empty state, directly reusing scripts/aws-export.sh's invocation."""
    accounts = []
    for env in ("Old", "New"):
        rows = [r for r in all_resources if r.aws_environment == env]
        ec2_count = sum(1 for r in rows if r.resource_type == "EC2")
        rds_count = sum(1 for r in rows if r.resource_type == "RDS")
        confirmed_count = sum(1 for r in rows if r.match_status == "confirmed")
        needs_import = len(rows) == 0
        if needs_import:
            summary = "No inventory imported yet"
            state = "Run the export below to populate this account"
            state_color = "var(--amber)"
        else:
            summary = f"{ec2_count} EC2 · {rds_count} RDS · {confirmed_count} matched to a customer"
            state = f"{len(rows)} real resources on file"
            state_color = "var(--green)"
        env_flag = env.lower()
        accounts.append({
            "name": f"{env} AWS",
            "region": None,
            "summary": summary,
            "state": state,
            "state_color": state_color,
            "needs_import": needs_import,
            "import_copy": (
                f"Their risk/capacity picture is computed without the {env} AWS account's real "
                f"data until this is imported."
            ) if needs_import else None,
            "import_cmd": f"./scripts/aws-export.sh {env_flag} <region>" if needs_import else None,
        })
    return accounts


def _hosting_breakdown(confirmed: list[AwsResource]) -> list[dict]:
    total = len(confirmed)
    if not total:
        return []
    counts: dict[str, int] = {}
    for r in confirmed:
        label = _hosting_model(r) or "Unknown"
        counts[label] = counts.get(label, 0) + 1
    out = []
    for label, count in sorted(counts.items(), key=lambda x: -x[1]):
        out.append({
            "label": label,
            "count": count,
            "share": f"{count / total * 100:.0f}%",
            "color": _HOSTING_COLORS.get(label, "var(--text3)"),
            "note": f"{count} of {total} confirmed resources",
        })
    return out


def _dependency_lifecycle(confirmed: list[AwsResource]) -> list[dict]:
    """Grouped by real (engine, major-version) among confirmed RDS
    resources. Lifecycle state comes from a small hardcoded, checkable
    real-world EOL table — never invented per-resource."""
    groups: dict[tuple[str, str], int] = {}
    for r in confirmed:
        if r.resource_type != "RDS" or not r.engine or not r.engine_version:
            continue
        major = r.engine_version.split(".")[0]
        groups[(r.engine, major)] = groups.get((r.engine, major), 0) + 1

    out = []
    for (engine, major), envs in sorted(groups.items(), key=lambda x: -x[1]):
        name = f"{engine} {major}"
        if engine.lower() in ("postgres", "postgresql") and major in _POSTGRES_EOL:
            eol_date, state = _POSTGRES_EOL[major]
            color = "var(--red)" if state == "End of life" else "var(--green)"
            state = f"{state} ({eol_date})"
        else:
            state = "Unknown"
            color = "var(--text3)"
        out.append({"name": name, "envs": f"{envs} env(s)", "state": state, "color": color})
    return out


def _aws_out(r: AwsResource) -> dict:
    return {
        "id": r.id,
        "resource_type": r.resource_type,
        "resource_id": r.resource_id,
        "name": r.name,
        "region": r.region,
        "aws_environment": r.aws_environment,
        "instance_type": r.instance_type,
        "engine": r.engine,
        "engine_version": r.engine_version,
        "state": r.state,
        "endpoint_or_ip": r.endpoint_or_ip,
        "launched_at": r.launched_at,
        "customer_id": r.customer_id,
        "customer_name": r.customer.name if r.customer else None,
        "customer_environment": r.customer_environment,
        "suggested_customer_id": r.suggested_customer_id,
        "match_status": r.match_status,
        "match_method": r.match_method,
        "imported_at": r.imported_at,
    }


# High-risk cutoff for the priority_score migration_priority() already
# computes (tier_weight + infra_weight + incident_severity_weight +
# defect_weight, max plausible ~12) — a plain code constant, matching the
# threshold convention already established for _CPU_UNDER_LOAD_PCT.
_HIGH_RISK_SCORE = 8


async def _attention_signals(
    db: AsyncSession, risk_customers: list[dict], confirmed_resources: list[AwsResource],
    latest_cpu_by_resource_id: dict[int, float | None],
) -> list[dict]:
    """The one genuinely new synthesis this page needed — customers hit by
    2+ DISTINCT real signals at once, mirroring the exact idiom already
    proven in services/observation_signals.py::cross_signal_candidates()
    (a different signal set, same "connect the dots, don't just list
    them" reasoning). Every signal here is a real, already-computed fact
    — nothing is invented for this function; it only groups and counts."""
    hot_customer_ids: set[int] = set()
    for r in confirmed_resources:
        cpu = latest_cpu_by_resource_id.get(r.id)
        if cpu is not None and cpu >= _CPU_UNDER_LOAD_PCT and r.customer_id:
            hot_customer_ids.add(r.customer_id)

    error_rows = (await db.execute(
        text(
            "SELECT ar.customer_id, count(*) FROM log_entries le "
            "JOIN aws_resources ar ON ar.id = le.aws_resource_id "
            "WHERE le.level = 'ERROR' AND ar.customer_id IS NOT NULL "
            "GROUP BY ar.customer_id"
        )
    )).all()
    error_count_by_customer = {row[0]: row[1] for row in error_rows}

    candidates = []
    for c in risk_customers:
        signals = []
        if c["infra"] == "Old":
            signals.append({"type": "old_infra", "detail": "Confirmed on Old AWS infrastructure"})
        if c["priority_score"] >= _HIGH_RISK_SCORE:
            signals.append({"type": "high_risk", "detail": f"Technical risk score {c['priority_score']}"})
        if c["open_incident_remediations"]:
            names = "; ".join(i["title"] for i in c["open_incident_remediations"][:2])
            signals.append({"type": "open_incident", "detail": names})
        if c["customer_id"] in hot_customer_ids:
            signals.append({"type": "hot_resource", "detail": f"AWS resource CPU ≥ {_CPU_UNDER_LOAD_PCT:.0f}%"})
        err_count = error_count_by_customer.get(c["customer_id"], 0)
        if err_count:
            signals.append({"type": "error_logs", "detail": f"{err_count} ERROR log line(s) on file"})

        if len(signals) >= 2:
            candidates.append({
                "customer_id": c["customer_id"],
                "customer_name": c["customer_name"],
                "customer_tier": c["customer_tier"],
                "priority_score": c["priority_score"],
                "signals": signals,
            })

    candidates.sort(key=lambda x: (-len(x["signals"]), -x["priority_score"]))
    return candidates


async def compute_estate_kpis(db: AsyncSession) -> dict:
    """The 4 real Overview KPIs — Estate / On Current Release / Customer
    Exposure / Legacy Footprint. Shared by the live overview() endpoint
    and the daily snapshot scheduler job so the two numbers can never
    silently disagree."""
    vms_customer_ids = set(
        (await db.execute(select(Customer.id).where(Customer.product.ilike("%VMS%")))).scalars().all()
    )
    estate_count = len(vms_customer_ids)

    latest_release_row = (await db.execute(select(Release).where(Release.is_latest == True))).scalar_one_or_none()  # noqa: E712
    latest_version = latest_release_row.version if latest_release_row else None

    tenant_prod = (
        await db.execute(
            select(CustomerTenantInfo).where(
                CustomerTenantInfo.customer_id.in_(vms_customer_ids), CustomerTenantInfo.environment == "PROD"
            )
        )
    ).scalars().all() if vms_customer_ids else []
    on_current_release_count = sum(
        1 for t in tenant_prod if t.release and latest_version and t.release == latest_version
    )

    exposure = await version_exposure(db=db)
    exposed_customer_ids: set[int] = set()
    for item in exposure:
        for c in item["reported_customers"]:
            exposed_customer_ids.add(c["id"])
        for c in item["silently_exposed_customers"]:
            exposed_customer_ids.add(c["id"])
    customer_exposure_count = len(exposed_customer_ids)

    legacy_confirmed = (
        await db.execute(
            select(AwsResource).where(AwsResource.match_status == "confirmed", AwsResource.aws_environment == "Old")
        )
    ).scalars().all()
    legacy_footprint_count = len({r.customer_id for r in legacy_confirmed if r.customer_id})

    return {
        "estate_count": estate_count,
        "on_current_release_count": on_current_release_count,
        "customer_exposure_count": customer_exposure_count,
        "legacy_footprint_count": legacy_footprint_count,
    }


async def _version_infra_matrix(db: AsyncSession, vms_customer_ids: set[int], latest_version: str | None) -> dict:
    """Real release band x hosting-type cross-tab, PROD-scoped. Every
    customer with no confirmed AWS resource shows under 'Unmatched' —
    honest, matching the current real (0-imported) state rather than
    hiding the gap."""
    tenant_prod = (
        await db.execute(
            select(CustomerTenantInfo).where(
                CustomerTenantInfo.customer_id.in_(vms_customer_ids), CustomerTenantInfo.environment == "PROD"
            )
        )
    ).scalars().all() if vms_customer_ids else []
    confirmed_prod = (
        await db.execute(
            select(AwsResource).where(AwsResource.match_status == "confirmed", AwsResource.customer_environment == "PROD")
        )
    ).scalars().all()
    resource_by_customer = {r.customer_id: r for r in confirmed_prod}

    bands = ["Current", "Supported", "Ageing", "Legacy", "End of life", "Unknown"]
    hosting_types = ["Docker / ECS", "EC2", "Legacy VM", "RDS", "Unmatched"]
    grid: dict[str, dict[str, int]] = {b: {h: 0 for h in hosting_types} for b in bands}

    for t in tenant_prod:
        band = _release_status(t.release, latest_version) or "Unknown"
        if band not in grid:
            band = "Unknown"
        resource = resource_by_customer.get(t.customer_id)
        hosting = (_hosting_model(resource) if resource else None) or "Unmatched"
        if hosting not in grid[band]:
            hosting = "Unmatched"
        grid[band][hosting] += 1

    rows = [
        {"band": b, "by_hosting": grid[b], "total": sum(grid[b].values())}
        for b in bands if sum(grid[b].values()) > 0
    ]
    return {"hosting_types": hosting_types, "rows": rows}


@router.get("/overview")
async def engineering_overview(db: AsyncSession = Depends(get_db)):
    exposure = await version_exposure(db=db)
    impact = await engineer_impact(db=db)
    missing = await missing_releases(db=db)
    below_latest = await customers_below_latest(db=db)
    distribution = await version_distribution(db=db)
    overdue_upgrades = await bug_fix_upgrades_overdue(db=db)
    pending_queue = await pending_upgrade_queue(db=db)
    risk = await migration_priority(db)

    vms_customer_ids = set(
        (await db.execute(select(Customer.id).where(Customer.product.ilike("%VMS%")))).scalars().all()
    )
    latest_release_row = (await db.execute(select(Release).where(Release.is_latest == True))).scalar_one_or_none()  # noqa: E712
    latest_version = latest_release_row.version if latest_release_row else None
    tenant_covered_ids = set(
        (await db.execute(
            select(CustomerTenantInfo.customer_id).where(
                CustomerTenantInfo.customer_id.in_(vms_customer_ids), CustomerTenantInfo.release.isnot(None)
            )
        )).scalars().all()
    )

    aws_rows = (await db.execute(select(AwsResource))).scalars().all()
    ec2_count = sum(1 for r in aws_rows if r.resource_type == "EC2")
    rds_count = sum(1 for r in aws_rows if r.resource_type == "RDS")
    confirmed = [r for r in aws_rows if r.match_status == "confirmed"]
    unmatched_count = sum(1 for r in aws_rows if r.match_status == "unmatched")
    internal_count = sum(1 for r in aws_rows if r.match_status == "internal")

    # infra_flag_cross_check: customers whose Customer.infra disagrees with
    # the real aws_environment of their confirmed AWS resource(s) — a new
    # validation signal nothing today checks.
    customers_by_id = {c.id: c for c in (await db.execute(select(Customer))).scalars().all()}
    mismatches = []
    legacy_confirmed_customer_ids: set[int] = set()
    for r in confirmed:
        cust = customers_by_id.get(r.customer_id)
        if not cust:
            continue
        if r.aws_environment == "Old":
            legacy_confirmed_customer_ids.add(cust.id)
        if cust.infra != "Mixed" and cust.infra != r.aws_environment:
            mismatches.append({
                "customer_id": cust.id, "customer_name": cust.name,
                "flagged_infra": cust.infra, "real_aws_environment": r.aws_environment,
                "resource_name": r.name or r.resource_id,
            })

    latest = (await db.execute(
        select(AwsResourceMetricSnapshot).order_by(AwsResourceMetricSnapshot.captured_at.desc())
    )).scalars().all()
    seen_resource_ids: set[int] = set()
    latest_cpu_by_resource_id: dict[int, float | None] = {}
    under_load = 0
    for snap in latest:
        if snap.aws_resource_id in seen_resource_ids:
            continue
        seen_resource_ids.add(snap.aws_resource_id)
        latest_cpu_by_resource_id[snap.aws_resource_id] = snap.cpu_utilization_pct
        if snap.cpu_utilization_pct is not None and snap.cpu_utilization_pct >= _CPU_UNDER_LOAD_PCT:
            under_load += 1

    attention = await _attention_signals(db, risk["customers"], confirmed, latest_cpu_by_resource_id)
    for c in attention:
        c["narrative"] = (
            f"{c['customer_name']} ({c['customer_tier']}) — "
            + "; ".join(s["detail"] for s in c["signals"]) + "."
        )

    kpis_now = await compute_estate_kpis(db)
    prior_snapshot = (
        await db.execute(
            select(EngineeringDailySnapshot)
            .where(EngineeringDailySnapshot.snapshot_date < date.today())
            .order_by(EngineeringDailySnapshot.snapshot_date.desc())
        )
    ).scalars().first()

    def _kpi(key: str) -> dict:
        value = kpis_now[key]
        delta = value - getattr(prior_snapshot, key) if prior_snapshot else None
        return {
            "value": value, "delta": delta,
            "since": prior_snapshot.snapshot_date.isoformat() if prior_snapshot else None,
        }

    kpis = {
        "estate": _kpi("estate_count"),
        "on_current_release": _kpi("on_current_release_count"),
        "customer_exposure": _kpi("customer_exposure_count"),
        "legacy_footprint": _kpi("legacy_footprint_count"),
    }

    version_infra_matrix = await _version_infra_matrix(db, vms_customer_ids, latest_version)

    return {
        "attention_signals": attention,
        "kpis": kpis,
        "version_infra_matrix": version_infra_matrix,
        "coverage": {
            "vms_customer_count": len(vms_customer_ids),
            "tenant_info_covered_count": len(tenant_covered_ids),
            "aws_resource_count": len(aws_rows),
            "aws_matched_customer_count": len({r.customer_id for r in confirmed if r.customer_id}),
        },
        "aws_coverage": {
            "ec2_count": ec2_count,
            "rds_count": rds_count,
            "confirmed_match_count": len(confirmed),
            "unmatched_count": unmatched_count,
            "internal_count": internal_count,
        },
        "infra_flag_cross_check": mismatches,
        "legacy_infra_customer_count": len(legacy_confirmed_customer_ids),
        "resources_under_load": under_load,
        "version_exposure": exposure[:10],
        "engineer_impact": impact[:10],
        "missing_releases": missing[:10],
        "customers_below_latest": below_latest,
        "version_distribution": distribution,
        "bug_fix_upgrades_overdue": overdue_upgrades,
        "pending_upgrade_queue_count": len(pending_queue),
        "technical_risk_top": risk["customers"][:10],
        "technical_risk_covered_count": risk.get("covered_count", 0),
        "technical_risk_vms_customer_count": risk.get("vms_customer_count", 0),
    }


@router.get("/environment-matrix")
async def environment_matrix(db: AsyncSession = Depends(get_db)):
    """Every real VMS customer x [PROD, TEST, DEV] — gaps shown explicitly
    (has_data: false), never silently omitted, per the confirmed 'full
    overview' decision. Mirrors CustomerDrillPanel.vue's Technical tab,
    which already loops these same three environments unconditionally for
    every customer."""
    vms_customers = (
        await db.execute(select(Customer).where(Customer.product.ilike("%VMS%")).order_by(Customer.name))
    ).scalars().all()
    vms_customer_ids = {c.id for c in vms_customers}

    tenant_rows = (
        await db.execute(select(CustomerTenantInfo).where(CustomerTenantInfo.customer_id.in_(vms_customer_ids)))
    ).scalars().all() if vms_customer_ids else []
    tenant_by_key = {(t.customer_id, t.environment): t for t in tenant_rows}

    confirmed_resources = (
        await db.execute(
            select(AwsResource).where(AwsResource.match_status == "confirmed", AwsResource.customer_id.in_(vms_customer_ids))
        )
    ).scalars().all() if vms_customer_ids else []
    resource_by_key = {(r.customer_id, r.customer_environment): r for r in confirmed_resources}

    latest_cpu_by_resource_id: dict[int, float | None] = {}
    if confirmed_resources:
        rows = (await db.execute(
            select(AwsResourceMetricSnapshot).order_by(AwsResourceMetricSnapshot.captured_at.desc())
        )).scalars().all()
        for snap in rows:
            latest_cpu_by_resource_id.setdefault(snap.aws_resource_id, snap.cpu_utilization_pct)

    # known/reported issue counts per customer — reuses version_exposure's
    # already-computed data rather than re-querying.
    exposure = await version_exposure(db=db)
    known_issues_by_customer: dict[int, int] = {}
    reported_issues_by_customer: dict[int, int] = {}
    for item in exposure:
        for c in item["silently_exposed_customers"]:
            known_issues_by_customer[c["id"]] = known_issues_by_customer.get(c["id"], 0) + 1
        for c in item["reported_customers"]:
            reported_issues_by_customer[c["id"]] = reported_issues_by_customer.get(c["id"], 0) + 1

    open_incidents = (
        await db.execute(
            select(IncidentRemediation.customer_id)
            .join(Incident, Incident.id == IncidentRemediation.incident_id)
            .where(Incident.status == "Open", IncidentRemediation.customer_id.in_(vms_customer_ids))
        )
    ).scalars().all() if vms_customer_ids else []
    incident_count_by_customer: dict[int, int] = {}
    for cid in open_incidents:
        incident_count_by_customer[cid] = incident_count_by_customer.get(cid, 0) + 1

    # Risk label per row — reuses migration_priority()'s one real,
    # already-shipped score (Technical Risk tab, Overview) rather than a
    # second scoring formula for this column. Same score for every
    # environment of a given customer, since the score itself is
    # customer-level, not per-environment.
    risk = await migration_priority(db)
    risk_score_by_customer = {c["customer_id"]: c["priority_score"] for c in risk["customers"]}

    latest_release_row = (await db.execute(select(Release).where(Release.is_latest == True))).scalar_one_or_none()  # noqa: E712
    latest_version = latest_release_row.version if latest_release_row else None

    rows = []
    for cust in vms_customers:
        for env in _ENVIRONMENTS:
            tenant = tenant_by_key.get((cust.id, env))
            resource = resource_by_key.get((cust.id, env))
            risk_score = risk_score_by_customer.get(cust.id)
            rows.append({
                "customer_id": cust.id,
                "customer_name": cust.name,
                "customer_tier": cust.tier,
                "customer_infra": cust.infra,
                "environment": env,
                "has_data": tenant is not None,
                "subdomain": tenant.subdomain if tenant else None,
                "release": tenant.release if tenant else None,
                # JVM-mode tenants respond on the /info endpoint just fine —
                # the problem is the data, not connectivity: confirmed live,
                # one JVM tenant's /info returned a legacy "6.38.3-R" while
                # its real version was 8.30.1. is_jvms_mode is only ever set
                # from a genuinely successful probe (the response itself
                # carries jvmsMode:true) — it says nothing about, and must
                # never be conflated with, a probe that failed to connect at
                # all (that's a separate, unrelated problem — almost always
                # a wrong/stale subdomain, not JVM mode).
                "is_jvms_mode": tenant.is_jvms_mode if tenant else None,
                "reported_environment": tenant.reported_environment if tenant else None,
                "last_synced_at": tenant.last_synced_at if tenant else None,
                "aws_resource": _aws_out(resource) if resource else None,
                "hosting_model": _hosting_model(resource),
                "release_status": _release_status(tenant.release if tenant else None, latest_version),
                "behind_current": bool(
                    tenant and tenant.release and latest_version and tenant.release != latest_version
                    and (_version_tuple(tenant.release) or ()) < (_version_tuple(latest_version) or ())
                ),
                "cpu_utilization_pct": latest_cpu_by_resource_id.get(resource.id) if resource else None,
                "known_issues_count": known_issues_by_customer.get(cust.id, 0) if env == "PROD" else None,
                "reported_issues_count": reported_issues_by_customer.get(cust.id, 0),
                "open_incident_count": incident_count_by_customer.get(cust.id, 0),
                "risk_score": risk_score,
                "risk_label": _risk_label(risk_score) if risk_score is not None else None,
            })

    return {
        "rows": rows,
        "vms_customer_count": len(vms_customers),
        "tenant_row_count": len(tenant_rows),
        "matched_aws_count": len(confirmed_resources),
    }


# A defect reported by 3+ distinct customers independently is treated as
# "critical" on the Versions page — reuses the same multi-customer-impact
# convention already established for sorting release_defects()/Fleet
# Version Exposure, not a fabricated severity field (VmsBug has none).
_CRITICAL_REPORT_THRESHOLD = 3


async def _known_defects_for_version(db: AsyncSession, version: str) -> list[dict]:
    """Real defects a customer on this exact release is still exposed to —
    Done bugs whose fix_version is a later version than this one, reusing
    version_exposure()'s exact reported/silently-exposed split."""
    v_tuple = _version_tuple(version)
    if not v_tuple:
        return []
    exposure = await version_exposure(db=db)
    out = []
    for item in exposure:
        fix_tuple = _version_tuple(item["fix_version"])
        if fix_tuple and fix_tuple > v_tuple:
            reported_count = len(item["reported_customers"])
            out.append({
                "vms_ref": item["vms_ref"],
                "fix_version": item["fix_version"],
                "reported_count": reported_count,
                "critical": reported_count >= _CRITICAL_REPORT_THRESHOLD,
            })
    out.sort(key=lambda d: -d["reported_count"])
    return out


@router.get("/versions")
async def list_versions(db: AsyncSession = Depends(get_db)):
    # Real Jira sync (sync_release_versions_from_jira) pulls the FULL real
    # version history — 674 rows spanning majors 2 through 8, most of it
    # ancient history no real customer runs. Scoped here to major 8, the
    # only major version any real VMS customer is actually on (confirmed
    # live via CustomerTenantInfo) — every row returned is still real,
    # just relevant.
    releases = (
        await db.execute(select(Release).where(Release.version.like("8.%")).order_by(Release.released_at.desc()))
    ).scalars().all()
    latest_release_row = next((r for r in releases if r.is_latest), None)
    latest_version = latest_release_row.version if latest_release_row else None

    tenant_rows = (await db.execute(select(CustomerTenantInfo))).scalars().all()
    total_tenant_rows = len(tenant_rows)
    envs_by_version: dict[str, int] = {}
    for t in tenant_rows:
        if t.release:
            envs_by_version[t.release] = envs_by_version.get(t.release, 0) + 1

    exposure = await version_exposure(db=db)

    out = []
    for r in releases:
        v_tuple = _version_tuple(r.version)
        defect_count = 0
        for item in exposure:
            fix_tuple = _version_tuple(item["fix_version"])
            if v_tuple and fix_tuple and fix_tuple > v_tuple:
                defect_count += 1
        envs = envs_by_version.get(r.version, 0)
        out.append({
            "version": r.version,
            "status": _release_status(r.version, latest_version),
            "released_at": r.released_at,
            "envs": envs,
            "share": f"{(envs / total_tenant_rows * 100):.0f}%" if total_tenant_rows else "0%",
            "known_defect_count": defect_count,
        })
    return out


@router.get("/versions/{version}")
async def version_detail(version: str, db: AsyncSession = Depends(get_db)):
    # Scoped to major 8 for the prev/next chain too — same reasoning as
    # list_versions(): real ancient majors 2-7 would otherwise show up as
    # a confusing "previous version" neighbor for an early 8.x release.
    releases = (
        await db.execute(select(Release).where(Release.version.like("8.%")).order_by(Release.released_at))
    ).scalars().all()
    release = next((r for r in releases if r.version == version), None)
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")
    latest_release_row = next((r for r in releases if r.is_latest), None)
    latest_version = latest_release_row.version if latest_release_row else None

    idx = releases.index(release)
    previous_version = releases[idx - 1].version if idx > 0 else None
    next_version = releases[idx + 1].version if idx < len(releases) - 1 else None

    tenant_rows = (
        await db.execute(select(CustomerTenantInfo).where(CustomerTenantInfo.release == version))
    ).scalars().all()
    total_tenant_rows = (await db.execute(select(CustomerTenantInfo))).scalars().all()
    customer_ids = {t.customer_id for t in tenant_rows}
    customers = {
        c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars().all()
    } if customer_ids else {}

    known_defects = await _known_defects_for_version(db, version)
    critical_count = sum(1 for d in known_defects if d["critical"])

    open_incidents = (
        await db.execute(
            select(IncidentRemediation)
            .join(Incident, Incident.id == IncidentRemediation.incident_id)
            .where(Incident.status == "Open", IncidentRemediation.customer_id.in_(customer_ids))
        )
    ).scalars().all() if customer_ids else []
    live_incident_count = len({i.id for i in open_incidents})

    age_days = (date.today() - release.released_at).days
    affected_names_ids = [{"id": cid, "name": customers[cid].name} for cid in customer_ids if cid in customers]
    affected_names_ids.sort(key=lambda x: x["name"])

    if not customer_ids:
        exposure_sentence = f"No environment currently reports {version} as its live release."
    elif known_defects:
        exposure_sentence = (
            f"{len(customer_ids)} real customer(s) are on {version}. If this release turns out to be the "
            f"problem, {len(known_defects)} known defect(s) — {critical_count} of them multi-customer-reported "
            f"— are still unresolved for this exact version."
        )
    else:
        exposure_sentence = (
            f"{len(customer_ids)} real customer(s) are on {version}, with no currently known unresolved defects "
            f"against this version."
        )

    return {
        "version": version,
        "status": _release_status(version, latest_version),
        "released_at": release.released_at,
        "age_days": age_days,
        "previous_version": previous_version,
        "next_version": next_version,
        "stats": {
            "environments": len(tenant_rows),
            "customers": len(customer_ids),
            "estate_share": f"{(len(tenant_rows) / len(total_tenant_rows) * 100):.0f}%" if total_tenant_rows else "0%",
            "known_defects": len(known_defects),
            "critical": critical_count,
            "live_incidents": live_incident_count,
        },
        "exposure_sentence": exposure_sentence,
        "affected_customers": affected_names_ids,
        "known_defects": known_defects,
    }


@router.get("/defects")
async def list_defects(db: AsyncSession = Depends(get_db)):
    """Not a Jira mirror — each real defect carries the chain Jira won't
    draw on its own: release -> environments still exposed -> customers ->
    open cases -> active incidents. Scoped to bugs with at least one real
    linked case (cases_by_bug_ref) — an internal Task/Story nobody ever
    complained about isn't a customer-facing defect. Real jira_ref stays
    the defect identity throughout — no second ID space invented."""
    all_bugs = (await db.execute(select(VmsBug))).scalars().all()
    by_bug_cases = await cases_by_bug_ref(db, {b.jira_ref for b in all_bugs})
    bugs = [b for b in all_bugs if by_bug_cases.get(b.jira_ref)]

    releases_by_version = {
        r.version.replace("-R", ""): r for r in (await db.execute(select(Release))).scalars().all()
    }
    tenant_rows = (await db.execute(select(CustomerTenantInfo))).scalars().all()

    open_incidents_by_ref: dict[str, int] = {}
    incidents = (
        await db.execute(select(Incident).where(Incident.status == "Open", Incident.linked_vms_ref.isnot(None)))
    ).scalars().all()
    for inc in incidents:
        open_incidents_by_ref[inc.linked_vms_ref] = open_incidents_by_ref.get(inc.linked_vms_ref, 0) + 1

    rows = []
    for b in bugs:
        cases = by_bug_cases.get(b.jira_ref, [])
        customer_ids = {c.customer_id for c in cases}
        title = cases[0].title if cases else b.jira_ref
        matched_release = releases_by_version.get(b.fix_version) if b.fix_version else None

        age_days = None
        if b.jira_created_at:
            created = b.jira_created_at if b.jira_created_at.tzinfo else b.jira_created_at.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - created).days

        fix_tuple = _version_tuple(b.fix_version) if b.fix_version else None
        exposed_env_count = 0
        if fix_tuple:
            for t in tenant_rows:
                t_tuple = _version_tuple(t.release) if t.release else None
                if t_tuple and t_tuple < fix_tuple:
                    exposed_env_count += 1

        incident_count = open_incidents_by_ref.get(b.jira_ref, 0)
        critical = len(customer_ids) >= _CRITICAL_REPORT_THRESHOLD or incident_count > 0
        chain = (
            f"{b.fix_version or 'no fix version'} → {exposed_env_count} environment(s) still exposed → "
            f"{len(customer_ids)} customer(s) → {len(cases)} case(s) → {incident_count} active incident(s)"
        )
        rows.append({
            "vms_ref": b.jira_ref,
            "title": title,
            "critical": critical,
            "status": b.status,
            "affects_count": len(customer_ids),
            "fix_version": b.fix_version,
            "fix_released": bool(matched_release),
            "age_days": age_days,
            "case_count": len(cases),
            "incident_count": incident_count,
            "exposed_env_count": exposed_env_count,
            "chain": chain,
        })

    rows.sort(key=lambda r: (-r["incident_count"], -r["affects_count"]))
    return rows


def _fam(version: str | None) -> str | None:
    """Version -> release-family label, e.g. '8.24.5-R' -> '8.24.x' —
    mirrors the mockup's own fam() helper, matching real minor-version
    grouping. Strips the '-R' suffix first (same convention already used
    everywhere else in this file) so real but inconsistently-suffixed
    tenant.release values don't produce a garbled family like '8.13-R.x'."""
    if not version:
        return None
    parts = version.replace("-R", "").split(".")
    return f"{parts[0]}.{parts[1]}.x" if len(parts) >= 2 else version


@router.get("/defects/{vms_ref}")
async def defect_panel(vms_ref: str, db: AsyncSession = Depends(get_db)):
    """The dedicated defect-entity panel — a real structured Impact Chain
    (release families -> production environments -> customers exposed ->
    open support cases -> active incidents) plus Exposed Customers
    (clickable — opens the SAME EngineeringEntityPanel targeted at that
    customer, not a second detail surface)."""
    bug = await db.get(VmsBug, vms_ref)
    if not bug:
        raise HTTPException(status_code=404, detail="Defect not found")

    by_bug_cases = await cases_by_bug_ref(db, {vms_ref})
    cases = by_bug_cases.get(vms_ref, [])
    customer_ids = sorted({c.customer_id for c in cases})
    title = cases[0].title if cases else vms_ref

    tenant_rows = (await db.execute(select(CustomerTenantInfo))).scalars().all()
    fix_tuple = _version_tuple(bug.fix_version) if bug.fix_version else None
    exposed_envs_all = [t for t in tenant_rows if t.release and fix_tuple and (_version_tuple(t.release) or ()) < fix_tuple]
    exposed_prod_envs = [t for t in exposed_envs_all if t.environment == "PROD"]
    family_counts: dict[str, int] = {}
    for t in exposed_envs_all:
        fam = _fam(t.release)
        if fam:
            family_counts[fam] = family_counts.get(fam, 0) + 1
    families_ranked = sorted(family_counts, key=lambda f: -family_counts[f])
    families_shown = families_ranked[:4]
    families_more = len(families_ranked) - len(families_shown)

    releases_by_version = {r.version.replace("-R", ""): r for r in (await db.execute(select(Release))).scalars().all()}
    matched_release = releases_by_version.get(bug.fix_version) if bug.fix_version else None

    open_cases_for_bug = [c for c in cases if c.status != "Closed"]
    incidents = (
        await db.execute(select(Incident).where(Incident.linked_vms_ref == vms_ref, Incident.status == "Open"))
    ).scalars().all()

    age_days = None
    if bug.jira_created_at:
        created = bug.jira_created_at if bug.jira_created_at.tzinfo else bug.jira_created_at.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - created).days

    customers = {
        c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars().all()
    } if customer_ids else {}
    affected_customers = [{"id": cid, "name": customers[cid].name} for cid in customer_ids if cid in customers]

    severity = "Critical" if (len(customer_ids) >= _CRITICAL_REPORT_THRESHOLD or incidents) else "High" if customer_ids else "Medium"
    families_detail = ", ".join(families_shown) + (f" +{families_more} more" if families_more > 0 else "") if families_shown else "—"
    prod_subdomains = sorted({t.subdomain or '' for t in exposed_prod_envs if t.subdomain})
    chain = [
        {"count": len(families_ranked), "label": "release family(ies)", "detail": families_detail, "color": "var(--accent)"},
        {"count": len(exposed_prod_envs), "label": "production environments", "detail": (", ".join(prod_subdomains[:5]) + (f" +{len(prod_subdomains) - 5} more" if len(prod_subdomains) > 5 else "")) if prod_subdomains else "no real environment data on file", "color": "var(--amber)" if exposed_prod_envs else "var(--text3)"},
        {"count": len(customer_ids), "label": "customers exposed", "detail": ", ".join(c["name"] for c in affected_customers[:3]) + (f" +{len(affected_customers) - 3} more" if len(affected_customers) > 3 else ""), "color": "var(--red)" if customer_ids else "var(--text3)"},
        {"count": len(open_cases_for_bug), "label": "open support cases", "detail": "already in the queue against these environments" if open_cases_for_bug else "none open right now", "color": "var(--amber)" if open_cases_for_bug else "var(--text3)"},
        {"count": len(incidents), "label": "active incidents", "detail": "live impact right now" if incidents else "no incident open for this defect", "color": "var(--red)" if incidents else "var(--text3)"},
    ]

    return {
        "kind": "defect",
        "kicker": f"{severity} defect · {bug.status}",
        "title": f"{vms_ref} — {title}",
        "sub": (
            f"owner {bug.assignee or 'unassigned'} · open {age_days if age_days is not None else '?'} days · "
            f"affects {families_detail} · "
            + (f"fixed in {bug.fix_version}" if bug.fix_version else "no fix version yet")
        ),
        "severity": severity,
        "status": bug.status,
        "fix_version": bug.fix_version,
        "fix_released": bool(matched_release),
        "age_days": age_days,
        "chain": chain,
        "affected_customers": affected_customers,
        "sprint_name": bug.sprint_name,
        "assignee": bug.assignee,
    }


@router.get("/deployments")
async def list_deployments(db: AsyncSession = Depends(get_db)):
    """Real deployment history — built entirely from the existing Upgrade
    pipeline's own completion records (to_version/environment/
    duration_minutes/verified_at), reframed as 'deployments' rather than a
    fictional CI/CD integration. 'Failed' has no dedicated real Upgrade
    stage today — scoped honestly to a labeled proxy (Cancelled), not
    invented false precision."""
    all_upgrades = (
        await db.execute(select(Upgrade).options(joinedload(Upgrade.customer)))
    ).scalars().all()

    since_7d = datetime.utcnow() - timedelta(days=7)
    verified = [u for u in all_upgrades if u.stage == "Verified Done"]
    verified_7d = [u for u in verified if u.verified_at and u.verified_at.replace(tzinfo=None) >= since_7d]
    cancelled_7d = [
        u for u in all_upgrades
        if u.stage == "Cancelled" and u.updated_at and u.updated_at.replace(tzinfo=None) >= since_7d
    ]
    total_7d = len(verified_7d) + len(cancelled_7d)
    success_rate = f"{(len(verified_7d) / total_7d * 100):.0f}%" if total_7d else "—"

    pending_stages = ("Requested", "DevOps Approval", "Cust. Confirmed")
    manual_remaining = sum(1 for u in all_upgrades if u.stage in pending_stages)

    stats = {
        "last_7_days": len(verified_7d),
        "success_rate": success_rate,
        "failed_cancelled_7d": len(cancelled_7d),
        "manual_deploys_remaining": manual_remaining,
    }

    # Deployment history table — most-recent completions first.
    verified.sort(key=lambda u: u.verified_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    deployments = []
    for u in verified[:100]:
        deployments.append({
            "id": u.id,
            "verified_at": u.verified_at,
            "customer_id": u.customer_id,
            "customer_name": u.customer.name if u.customer else None,
            "environment": u.environment,
            "move": f"{u.from_version or '?'} → {u.to_version}",
            "duration_minutes": u.duration_minutes,
            "status": "Verified",
            "note": u.blocked_reason or u.after_hours_billing_note or "",
        })

    # 8.30.1-style rollout funnel against the real latest release.
    latest_release_row = (await db.execute(select(Release).where(Release.is_latest == True))).scalar_one_or_none()  # noqa: E712
    latest_version = latest_release_row.version if latest_release_row else None
    vms_customer_ids = set(
        (await db.execute(select(Customer.id).where(Customer.product.ilike("%VMS%")))).scalars().all()
    )
    prod_rows = (
        await db.execute(
            select(CustomerTenantInfo).where(
                CustomerTenantInfo.customer_id.in_(vms_customer_ids), CustomerTenantInfo.environment == "PROD"
            )
        )
    ).scalars().all() if vms_customer_ids else []
    active_prod_upgrade_customer_ids = {
        u.customer_id for u in all_upgrades
        if u.environment == "PROD" and u.stage not in ("Verified Done", "Cancelled")
    }
    on_release = sum(1 for t in prod_rows if t.release == latest_version)
    blocked_count = sum(1 for u in all_upgrades if u.blocked and u.stage not in ("Verified Done", "Cancelled"))
    scheduled_count = sum(1 for u in all_upgrades if u.stage in ("Scheduled", "In Progress"))
    eligible_not_scheduled = sum(
        1 for t in prod_rows
        if t.release != latest_version and t.customer_id not in active_prod_upgrade_customer_ids
    )
    rollout_total = max(len(prod_rows), 1)
    rollout = [
        {"label": "On release", "count": on_release, "share": f"{on_release / rollout_total * 100:.0f}%", "color": "var(--green)", "note": f"already on {latest_version}" if latest_version else "no latest release on file"},
        {"label": "Eligible, not scheduled", "count": eligible_not_scheduled, "share": f"{eligible_not_scheduled / rollout_total * 100:.0f}%", "color": "var(--accent)", "note": "behind, no active upgrade in flight"},
        {"label": "Blocked", "count": blocked_count, "share": f"{blocked_count / rollout_total * 100:.0f}%", "color": "var(--red)", "note": "active upgrade currently blocked"},
        {"label": "Scheduled", "count": scheduled_count, "share": f"{scheduled_count / rollout_total * 100:.0f}%", "color": "var(--amber)", "note": "Scheduled or In Progress"},
    ]

    upcoming = [
        u for u in all_upgrades
        if u.scheduled_at and u.stage in ("Scheduled", "Cust. Confirmed") and u.scheduled_at.replace(tzinfo=None) >= datetime.utcnow()
    ]
    upcoming.sort(key=lambda u: u.scheduled_at)
    upcoming_out = [
        {
            "when": u.scheduled_at.strftime("%b %d") if u.scheduled_at else "—",
            "what": f"{u.customer.name if u.customer else 'Unknown'} — {u.environment} → {u.to_version}",
        }
        for u in upcoming[:10]
    ]

    return {
        "stats": stats,
        "deployments": deployments,
        "rollout": {"target_version": latest_version, "buckets": rollout},
        "upcoming": upcoming_out,
    }


async def _compute_customer_risk_context(db: AsyncSession, customer_id: int) -> dict | None:
    """Shared by /customer-technical (Support/CS's CustomerDrillPanel) and
    /customer-panel (the new dedicated Engineering panel) so both read the
    exact same real numbers — reuses migration_priority()'s real,
    already-shipped 4-factor score (decomposed for display, not replaced
    by a second formula, per the explicit Option-B decision) plus the
    real upgrade-path chain, PROD/TEST/DEV material-difference diff, and
    'Connected' section (real defects + real peer customers on the same
    version)."""
    customer = await db.get(Customer, customer_id)
    if not customer:
        return None

    risk = await migration_priority(db)
    risk_row = next((c for c in risk["customers"] if c["customer_id"] == customer_id), None)

    releases = (await db.execute(select(Release).order_by(Release.released_at))).scalars().all()
    upgrade_path: list[str] = []
    if risk_row and risk_row["current_version"]:
        cur_tuple = _version_tuple(risk_row["current_version"])
        for r in releases:
            r_tuple = _version_tuple(r.version)
            if cur_tuple and r_tuple and r_tuple >= cur_tuple:
                upgrade_path.append(r.version)

    tenant_rows = (
        await db.execute(select(CustomerTenantInfo).where(CustomerTenantInfo.customer_id == customer_id))
    ).scalars().all()
    tenant_by_env = {t.environment: t for t in tenant_rows}
    releases_present = {t.release for t in tenant_rows if t.release}
    material_diff = len(releases_present) > 1
    env_diff = {
        env: {
            "release": tenant_by_env[env].release if env in tenant_by_env else None,
            "has_data": env in tenant_by_env,
            # See the matching comment in environment_matrix() — JVM-mode
            # tenants' /info release isn't reliable.
            "is_jvms_mode": tenant_by_env[env].is_jvms_mode if env in tenant_by_env else None,
        }
        for env in _ENVIRONMENTS
    }

    exposure = await version_exposure(db=db)
    connected_defects = []
    for item in exposure:
        reported_ids = {c["id"] for c in item["reported_customers"]}
        exposed_ids = {c["id"] for c in item["silently_exposed_customers"]}
        if customer_id in reported_ids or customer_id in exposed_ids:
            connected_defects.append({
                "vms_ref": item["vms_ref"], "fix_version": item["fix_version"],
                "reported": customer_id in reported_ids,
            })

    peer_customers = []
    if risk_row and risk_row["current_version"]:
        peer_ids = set(
            (await db.execute(
                select(CustomerTenantInfo.customer_id).where(
                    CustomerTenantInfo.release == risk_row["current_version"],
                    CustomerTenantInfo.customer_id != customer_id,
                )
            )).scalars().all()
        )
        if peer_ids:
            peers = (await db.execute(select(Customer).where(Customer.id.in_(peer_ids)))).scalars().all()
            peer_customers = [{"id": p.id, "name": p.name} for p in peers]

    return {
        "customer_id": customer_id,
        "risk": risk_row,
        "upgrade_path": upgrade_path,
        "env_diff": env_diff,
        "material_diff": material_diff,
        "connected_defects": connected_defects,
        "peer_customers": peer_customers,
    }


@router.get("/customer-technical/{customer_id}")
async def customer_technical(customer_id: int, db: AsyncSession = Depends(get_db)):
    ctx = await _compute_customer_risk_context(db, customer_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return ctx


_RED, _AMBER, _GREEN, _MUTED = "var(--red)", "var(--amber)", "var(--green)", "var(--text3)"


@router.get("/customer-panel/{customer_id}")
async def customer_panel(customer_id: int, focus_env: str | None = None, db: AsyncSession = Depends(get_db)):
    """The dedicated Engineering entity panel — genuinely different from
    CustomerDrillPanel (Support/CS's own 360, untouched) and BugDrillPanel.
    One real, config-driven panel matching the mockup's own architecture:
    Customer Reports triage (5 real checks — the 6th, symptom-tagged
    defect matching, is honestly skipped, no symptom taxonomy exists on
    VmsBug), Environments Side-by-Side, What Changed, Incident & Case
    History, Technical Risk, Release/Infrastructure/Engineering-Health
    blocks, Known Issues & Runbooks, Connected."""
    customer = await db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    ctx = await _compute_customer_risk_context(db, customer_id)
    risk_row = ctx["risk"] if ctx else None

    tenant_rows = (
        await db.execute(select(CustomerTenantInfo).where(CustomerTenantInfo.customer_id == customer_id))
    ).scalars().all()
    tenant_by_env = {t.environment: t for t in tenant_rows}

    resources = (
        await db.execute(select(AwsResource).where(AwsResource.customer_id == customer_id, AwsResource.match_status == "confirmed"))
    ).scalars().all()
    resource_by_env = {r.customer_environment: r for r in resources}
    prod_resource = resource_by_env.get("PROD")

    latest_cpu_by_resource_id: dict[int, float | None] = {}
    if resources:
        snaps = (
            await db.execute(
                select(AwsResourceMetricSnapshot)
                .where(AwsResourceMetricSnapshot.aws_resource_id.in_([r.id for r in resources]))
                .order_by(AwsResourceMetricSnapshot.captured_at.desc())
            )
        ).scalars().all()
        for s in snaps:
            latest_cpu_by_resource_id.setdefault(s.aws_resource_id, s.cpu_utilization_pct)
    prod_cpu = latest_cpu_by_resource_id.get(prod_resource.id) if prod_resource else None

    prod_tenant = tenant_by_env.get("PROD")
    prod_release = prod_tenant.release if prod_tenant else None
    known_defects = await _known_defects_for_version(db, prod_release) if prod_release else []

    latest_release_row = (await db.execute(select(Release).where(Release.is_latest == True))).scalar_one_or_none()  # noqa: E712
    latest_version = latest_release_row.version if latest_release_row else None
    prod_release_row = (
        (await db.execute(select(Release).where(Release.version == prod_release))).scalar_one_or_none()
        if prod_release else None
    )

    # ---------- Environments side by side ----------
    def _env_cell(env: str, fn):
        t, r = tenant_by_env.get(env), resource_by_env.get(env)
        if not t and not r:
            return None
        return fn(t, r)

    drift_defs = [
        # JVM-mode tenants' /info release isn't reliable (see the matching
        # comment in environment_matrix()) — flagged inline here since this
        # table's cells are plain display strings, not structured objects.
        ("Release", lambda t, r: (f"{t.release} ⚠ JVM" if t.is_jvms_mode else t.release) if t and t.release else None),
        ("Subdomain", lambda t, r: t.subdomain if t else None),
        ("Hosting", lambda t, r: _hosting_model(r) if r else None),
        ("Database", lambda t, r: f"{r.engine} {r.engine_version}" if r and r.engine else None),
        ("AWS resource", lambda t, r: r.resource_id if r else None),
        ("CPU (snapshot)", lambda t, r: (f"{latest_cpu_by_resource_id.get(r.id)}%" if r and latest_cpu_by_resource_id.get(r.id) is not None else ("not imported" if r else None))),
    ]
    drift_rows = []
    material_diff_labels = []
    for label, fn in drift_defs:
        cells = {env: _env_cell(env, fn) for env in _ENVIRONMENTS}
        real_vals = {v for v in cells.values() if v is not None}
        if len(real_vals) > 1:
            material_diff_labels.append(label)
        drift_rows.append({"label": label, "cells": cells})
    drift_count = len(material_diff_labels)

    # ---------- Real cases / incidents for this customer ----------
    open_cases = (
        await db.execute(select(Case).where(Case.customer_id == customer_id, Case.status != "Closed"))
    ).scalars().all()
    open_remediations = (
        await db.execute(
            select(IncidentRemediation, Incident)
            .join(Incident, Incident.id == IncidentRemediation.incident_id)
            .where(IncidentRemediation.customer_id == customer_id, Incident.status == "Open")
        )
    ).all()

    # ---------- What changed (real Upgrade history + incident opens) ----------
    upgrades = (
        await db.execute(select(Upgrade).where(Upgrade.customer_id == customer_id).order_by(Upgrade.updated_at.desc()))
    ).scalars().all()
    now = datetime.now(timezone.utc)
    recent_upgrades = [
        u for u in upgrades
        if u.updated_at and (u.updated_at if u.updated_at.tzinfo else u.updated_at.replace(tzinfo=timezone.utc)) >= now - timedelta(hours=24)
    ]

    timeline = []
    for u in upgrades[:15]:
        if u.stage == "Verified Done" and u.verified_at:
            timeline.append({
                "when": u.verified_at, "mark": "▲", "color": _GREEN,
                "what": f"{u.from_version or '?'} → {u.to_version} verified on {u.environment}", "link": "",
            })
        elif u.blocked:
            timeline.append({
                "when": u.updated_at, "mark": "✕", "color": _RED,
                "what": f"{u.environment} upgrade to {u.to_version} blocked", "link": u.blocked_reason or "",
            })
        else:
            timeline.append({
                "when": u.updated_at, "mark": "◆", "color": _AMBER,
                "what": f"{u.environment} upgrade to {u.to_version} — {u.stage}", "link": "",
            })
    for rem, inc in open_remediations:
        timeline.append({"when": inc.detected_at, "mark": "●", "color": _RED, "what": f"Incident opened — {inc.title}", "link": ""})
    timeline.sort(key=lambda t: t["when"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    # ---------- Incident & case history ----------
    history = []
    for rem, inc in open_remediations:
        history.append({"when": "open", "ref": f"INC-{inc.id}", "what": inc.title, "state": "Open", "color": _RED})
    if open_cases:
        oldest = max((c.days_open or 0) for c in open_cases)
        history.append({
            "when": "open", "ref": open_cases[0].jira_ref, "what": f"{len(open_cases)} open support case(s) · oldest {oldest} days",
            "state": "L2", "color": _AMBER,
        })
    repeat_count = len(open_remediations)
    repeat = f"{repeat_count} open incident(s) this customer" if repeat_count >= 2 else ("One open incident" if repeat_count == 1 else "No repeat pattern")

    # ---------- Customer Reports triage — 5 real checks ----------
    checks = []
    checks.append({
        "mark": "●" if recent_upgrades else "○", "color": _AMBER if recent_upgrades else _GREEN,
        "label": "Changed in the last 24h" if recent_upgrades else "No upgrade activity in the last 24h",
        "detail": "; ".join(f"{u.environment} → {u.to_version} ({u.stage})" for u in recent_upgrades) if recent_upgrades else "Unlikely to be a change-induced regression.",
    })

    error_count = 0
    if resources:
        error_rows = (
            await db.execute(
                text(
                    "SELECT count(*) FROM log_entries WHERE level = 'ERROR' AND aws_resource_id = ANY(:ids) "
                    "AND timestamp >= :since"
                ),
                {"ids": [r.id for r in resources], "since": now - timedelta(hours=24)},
            )
        ).scalar_one()
        error_count = error_rows or 0
    checks.append({
        "mark": "●" if error_count else "○", "color": _RED if error_count > 1 else (_AMBER if error_count else _GREEN),
        "label": f"{error_count} ERROR log line(s) in the last 24h" if error_count else ("No errors in the last 24h" if resources else "No logs imported for this account"),
        "detail": "" if resources else "No AWS resource matched — silence here is a blind spot, not a clean bill of health.",
    })

    checks.append({
        "mark": "○", "color": _AMBER,
        "label": "No application-level load metrics imported",
        "detail": "Capacity beyond raw CPU is an unknown for this account until app-level metrics exist.",
    })

    checks.append({
        "mark": "●" if drift_count else "○", "color": _AMBER if drift_count else _GREEN,
        "label": f"{drift_count} kind(s) of environment drift" if drift_count else "Environments are aligned",
        "detail": ", ".join(material_diff_labels) if drift_count else "A TEST reproduction should be trustworthy.",
    })

    checks.append({
        "mark": "●" if (open_cases or open_remediations) else "○", "color": _AMBER if (open_cases or open_remediations) else _MUTED,
        "label": f"{len(open_cases)} open case(s), {len(open_remediations)} active incident(s)",
        "detail": "Already an incident — do not open a second one." if open_remediations else "No incident open yet.",
    })

    fired = [c for c in checks if c["mark"] == "●"]
    if recent_upgrades:
        verdict = f"{customer.name} had real change activity in the last 24 hours — start with the change before anything else."
    elif error_count:
        verdict = f"{error_count} real ERROR log line(s) on file for {customer.name} in the last 24 hours."
    elif drift_count:
        verdict = f"PROD and TEST differ in {drift_count} real way(s) for {customer.name} — a TEST reproduction may not be valid."
    elif not fired:
        verdict = f"Nothing in change history, logs, or environment drift explains an issue for {customer.name} right now."
    else:
        verdict = f"{len(fired)} real signal(s) are flagged for {customer.name} — see the checklist below."

    # ---------- Blocks ----------
    blocks = []
    running_v = prod_release or "no data on file"
    if prod_tenant and prod_tenant.is_jvms_mode and prod_release:
        running_v = f"{prod_release} — ⚠ JVM-mode, /info unreliable"
    release_rows = [
        {"k": "Running", "v": running_v, "color": "var(--amber)" if (prod_tenant and prod_tenant.is_jvms_mode) else None},
        {"k": "Released", "v": prod_release_row.released_at.isoformat() if prod_release_row else "unknown", "color": None},
        {"k": "Latest available", "v": latest_version or "—", "color": None},
    ]
    if ctx and ctx["upgrade_path"]:
        path = ctx["upgrade_path"]
        shown = path if len(path) <= 5 else [path[0], "…", path[-1]]
        release_rows.append({"k": "Upgrade path", "v": " → ".join(shown), "color": None})
    blocks.append({"title": "Release", "rows": release_rows})

    infra_rows = [{"k": "Hosting", "v": _hosting_model(prod_resource) or "unmatched — no AWS resource on file", "color": None}]
    if prod_resource:
        infra_rows.append({"k": "AWS resource", "v": prod_resource.resource_id, "color": None})
        if prod_resource.engine:
            infra_rows.append({"k": "Database", "v": f"{prod_resource.engine} {prod_resource.engine_version or ''}".strip(), "color": None})
        infra_rows.append({"k": "CPU (snapshot)", "v": f"{prod_cpu}%" if prod_cpu is not None else "not imported", "color": _RED if (prod_cpu or 0) > 85 else None})
    blocks.append({"title": "Infrastructure", "rows": infra_rows})

    blocks.append({"title": "Engineering Health", "rows": [
        {"k": "Open bugs", "v": f"{len(known_defects)} open, {sum(1 for d in known_defects if d['critical'])} critical for this release", "color": None},
        {"k": "Active incidents", "v": f"{len(open_remediations)} open", "color": _RED if open_remediations else None},
        {"k": "Support cases", "v": f"{len(open_cases)} open with L2", "color": _AMBER if open_cases else None},
        {"k": "Known issues", "v": ", ".join(d["vms_ref"] for d in known_defects[:5]) or "none on file", "color": None},
    ]})

    # ---------- Known issues & runbooks ----------
    knowledge = [
        {"kind": "Known issue", "color": _RED if d["critical"] else _AMBER, "what": d["vms_ref"], "meta": f"fix {d['fix_version']}" if d["fix_version"] else "no fix version"}
        for d in known_defects
    ]
    runbooks = (await db.execute(select(Runbook))).scalars().all()
    hosting_now = _hosting_model(prod_resource)
    db_now = f"{prod_resource.engine} {prod_resource.engine_version}" if prod_resource and prod_resource.engine else ""
    for rb in runbooks:
        if rb.trigger_hosting_model and rb.trigger_hosting_model != hosting_now:
            continue
        if rb.trigger_engine_contains and rb.trigger_engine_contains not in db_now:
            continue
        knowledge.append({"kind": "Runbook", "color": "var(--accent)", "what": rb.title, "meta": rb.ref})

    return {
        "kind": "customer",
        "kicker": f"{customer.tier} customer · {len(tenant_rows)} environment(s)",
        "title": customer.name,
        "sub": (
            f"{prod_resource.resource_id if prod_resource else 'no AWS resource matched'} · "
            f"production on {prod_release or 'no data on file'}"
            + (f" · opened from {focus_env}" if focus_env else "")
        ),
        "triage": {"color": _RED if error_count > 1 or recent_upgrades else (_AMBER if fired else "var(--accent)"), "verdict": verdict, "checks": checks},
        "drift": {"rows": drift_rows, "note": f"{drift_count} kind(s) of drift" if drift_count else "environments aligned"},
        "load_available": False,
        "timeline": [
            {"when": t["when"].strftime("%d %b %H:%M") if t["when"] else "—", "mark": t["mark"], "color": t["color"], "what": t["what"], "link": t["link"]}
            for t in timeline[:12]
        ],
        "history": history,
        "repeat": repeat,
        "risk": risk_row,
        "blocks": blocks,
        "knowledge": knowledge,
        "connected_defects": ctx["connected_defects"] if ctx else [],
        "peer_customers": ctx["peer_customers"] if ctx else [],
    }


def _runbook_out(r: Runbook) -> dict:
    return {
        "id": r.id, "ref": r.ref, "title": r.title,
        "trigger_hosting_model": r.trigger_hosting_model, "trigger_engine_contains": r.trigger_engine_contains,
        "body": r.body, "created_at": r.created_at, "updated_at": r.updated_at,
    }


@router.get("/runbooks")
async def list_runbooks(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Runbook).order_by(Runbook.ref))).scalars().all()
    return [_runbook_out(r) for r in rows]


@router.post("/runbooks", status_code=201)
async def create_runbook(data: dict, db: AsyncSession = Depends(get_db)):
    ref, title, body = data.get("ref"), data.get("title"), data.get("body")
    if not ref or not title or not body:
        raise HTTPException(status_code=400, detail="ref, title, and body are required")
    existing = (await db.execute(select(Runbook).where(Runbook.ref == ref))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Runbook {ref} already exists")
    rb = Runbook(
        ref=ref, title=title, body=body,
        trigger_hosting_model=data.get("trigger_hosting_model"),
        trigger_engine_contains=data.get("trigger_engine_contains"),
    )
    db.add(rb)
    await db.commit()
    await db.refresh(rb)
    return _runbook_out(rb)


@router.patch("/runbooks/{runbook_id}")
async def update_runbook(runbook_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    rb = await db.get(Runbook, runbook_id)
    if not rb:
        raise HTTPException(status_code=404, detail="Runbook not found")
    for field in ("title", "body", "trigger_hosting_model", "trigger_engine_contains"):
        if field in data:
            setattr(rb, field, data[field])
    await db.commit()
    await db.refresh(rb)
    return _runbook_out(rb)


@router.delete("/runbooks/{runbook_id}", status_code=204)
async def delete_runbook(runbook_id: int, db: AsyncSession = Depends(get_db)):
    rb = await db.get(Runbook, runbook_id)
    if not rb:
        raise HTTPException(status_code=404, detail="Runbook not found")
    await db.delete(rb)
    await db.commit()


@router.post("/aws-import")
async def aws_import(data: dict, db: AsyncSession = Depends(get_db)):
    aws_environment = data.get("aws_environment")
    if aws_environment not in ("Old", "New"):
        raise HTTPException(status_code=400, detail="aws_environment must be 'Old' or 'New'")
    region = data.get("region")

    parsed: list[dict] = []
    if data.get("ec2"):
        parsed += parse_ec2(data["ec2"])
    if data.get("rds"):
        parsed += parse_rds(data["rds"])
    cw_by_key = parse_cloudwatch(data.get("cloudwatch") or [])

    by_name, by_subdomain = await build_match_maps(db)

    created = updated = suggested = 0
    for item in parsed:
        existing = (
            await db.execute(
                select(AwsResource).where(
                    AwsResource.resource_type == item["resource_type"],
                    AwsResource.resource_id == item["resource_id"],
                    AwsResource.aws_environment == aws_environment,
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            candidate = match_candidate(item["name"], by_name, by_subdomain)
            row = AwsResource(
                resource_type=item["resource_type"],
                resource_id=item["resource_id"],
                name=item["name"],
                region=region,
                aws_environment=aws_environment,
                instance_type=item["instance_type"],
                engine=item["engine"],
                engine_version=item["engine_version"],
                state=item["state"],
                endpoint_or_ip=item["endpoint_or_ip"],
                launched_at=item["launched_at"],
                raw_json=item["raw"],
                suggested_customer_id=candidate.id if candidate else None,
            )
            db.add(row)
            created += 1
            if candidate:
                suggested += 1
            await db.flush()  # need row.id for the metric snapshot below
        else:
            existing.name = item["name"]
            existing.region = region or existing.region
            existing.instance_type = item["instance_type"]
            existing.engine = item["engine"]
            existing.engine_version = item["engine_version"]
            existing.state = item["state"]
            existing.endpoint_or_ip = item["endpoint_or_ip"]
            existing.launched_at = item["launched_at"]
            existing.raw_json = item["raw"]
            existing.updated_at = datetime.utcnow()
            row = existing
            updated += 1

        cw = cw_by_key.get((item["resource_type"], item["resource_id"]))
        if cw:
            db.add(AwsResourceMetricSnapshot(
                aws_resource_id=row.id,
                captured_at=cw["captured_at"],
                cpu_utilization_pct=cw["cpu_utilization_pct"],
                raw_json=cw["raw"],
            ))

    db.add(AuditLog(
        actor="you", action="aws_import.uploaded", target_type="aws_import", target_id=aws_environment,
        detail=f"created={created} updated={updated} suggested={suggested}",
    ))
    await db.commit()
    return {"created": created, "updated": updated, "suggested": suggested}


@router.get("/infrastructure")
async def infrastructure_summary(db: AsyncSession = Depends(get_db)):
    """Per-account cards + Hosting Model + Dependency Lifecycle — the
    Infrastructure tab's summary panels. Inventory itself stays on the
    existing /aws-resources endpoint (unchanged, already used for the
    import/unmatched-resolution flow)."""
    all_resources = (await db.execute(select(AwsResource))).scalars().all()
    confirmed = [r for r in all_resources if r.match_status == "confirmed"]
    return {
        "accounts": _infra_accounts(all_resources),
        "hosting": _hosting_breakdown(confirmed),
        "dependency_lifecycle": _dependency_lifecycle(confirmed),
    }


@router.get("/aws-resources")
async def list_aws_resources(match_status: str | None = None, db: AsyncSession = Depends(get_db)):
    query = select(AwsResource).options(joinedload(AwsResource.customer)).order_by(AwsResource.name)
    if match_status:
        query = query.where(AwsResource.match_status == match_status)
    rows = (await db.execute(query)).scalars().all()
    return [_aws_out(r) for r in rows]


@router.post("/aws-resources/{resource_id}/confirm-match")
async def confirm_aws_match(resource_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    row = await db.get(AwsResource, resource_id)
    if not row:
        raise HTTPException(status_code=404, detail="AWS resource not found")
    customer_id = data.get("customer_id")
    environment = data.get("environment")
    if not customer_id or environment not in _ENVIRONMENTS:
        raise HTTPException(status_code=400, detail="customer_id and a valid environment are required")

    row.customer_id = customer_id
    row.customer_environment = environment
    row.match_status = "confirmed"
    row.match_method = "name_heuristic" if customer_id == row.suggested_customer_id else "manual"
    row.updated_at = datetime.utcnow()
    db.add(AuditLog(
        actor="you", action="aws_resource.match_confirmed", target_type="aws_resource", target_id=str(resource_id),
        detail=f"customer_id={customer_id} environment={environment} method={row.match_method}",
    ))
    await db.commit()
    await db.refresh(row, attribute_names=["customer"])
    return _aws_out(row)


@router.post("/aws-resources/{resource_id}/mark-internal")
async def mark_aws_internal(resource_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(AwsResource, resource_id)
    if not row:
        raise HTTPException(status_code=404, detail="AWS resource not found")
    row.match_status = "internal"
    row.updated_at = datetime.utcnow()
    db.add(AuditLog(actor="you", action="aws_resource.marked_internal", target_type="aws_resource", target_id=str(resource_id)))
    await db.commit()
    return _aws_out(row)


def _log_out(r: LogEntry) -> dict:
    return {
        "id": r.id,
        "log_type": r.log_type,
        "source_group": r.source_group,
        "event_id": r.event_id,
        "timestamp": r.timestamp,
        "message": r.message,
        "level": r.level,
        "aws_resource_id": r.aws_resource_id,
        "aws_resource_name": r.resource.name if r.resource else None,
        "customer_id": r.resource.customer_id if r.resource else None,
        "customer_name": r.resource.customer.name if r.resource and r.resource.customer else None,
        "imported_at": r.imported_at,
    }


@router.post("/log-import")
async def log_import(data: dict, db: AsyncSession = Depends(get_db)):
    log_type = data.get("log_type")
    if log_type not in _LOG_TYPES:
        raise HTTPException(status_code=400, detail=f"log_type must be one of {_LOG_TYPES}")
    source_group = data.get("source_group")
    if not source_group:
        raise HTTPException(status_code=400, detail="source_group is required")
    aws_resource_id = data.get("aws_resource_id")
    if aws_resource_id is not None and not await db.get(AwsResource, aws_resource_id):
        raise HTTPException(status_code=400, detail="aws_resource_id does not exist")

    entries = data.get("entries")
    if not entries:
        raise HTTPException(status_code=400, detail="entries is required")

    if log_type == "cloudtrail":
        parsed = parse_cloudtrail_events(entries)
    else:
        parsed = parse_cloudwatch_log_events(entries, log_type)

    created = skipped = 0
    for item in parsed:
        existing = (
            await db.execute(
                select(LogEntry).where(
                    LogEntry.log_type == log_type,
                    LogEntry.source_group == source_group,
                    LogEntry.event_id == item["event_id"],
                )
            )
        ).scalar_one_or_none()
        if existing:
            skipped += 1
            continue
        db.add(LogEntry(
            log_type=log_type,
            source_group=source_group,
            event_id=item["event_id"],
            timestamp=item["timestamp"],
            message=item["message"],
            level=item["level"],
            raw_json=item["raw"],
            aws_resource_id=aws_resource_id,
        ))
        created += 1

    db.add(AuditLog(
        actor="you", action="log_import.uploaded", target_type="log_entries", target_id=source_group,
        detail=f"log_type={log_type} created={created} skipped={skipped}",
    ))
    await db.commit()
    return {"created": created, "skipped": skipped}


@router.get("/logs")
async def search_logs(
    q: str | None = None,
    log_type: str | None = None,
    aws_resource_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    """Full-text search over imported log entries — Postgres tsvector, the
    same precedent already proven for OllamaSearchIndex. Not a query
    language; not live tail. A real, bounded search over whatever's been
    imported so far."""
    limit = min(limit, _MAX_LOG_RESULTS)

    if q:
        conditions = ["message_tsv @@ plainto_tsquery('english', :q)"]
        params: dict = {"q": q, "limit": limit}
        order = "ts_rank(message_tsv, plainto_tsquery('english', :q)) DESC, timestamp DESC"
    else:
        conditions = []
        params = {"limit": limit}
        order = "timestamp DESC"

    if log_type:
        conditions.append("log_type = :log_type")
        params["log_type"] = log_type
    if aws_resource_id:
        conditions.append("aws_resource_id = :aws_resource_id")
        params["aws_resource_id"] = aws_resource_id
    if since:
        conditions.append("timestamp >= :since")
        params["since"] = since
    if until:
        conditions.append("timestamp <= :until")
        params["until"] = until

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = (
        await db.execute(
            text(f"SELECT id FROM log_entries {where_clause} ORDER BY {order} LIMIT :limit"),
            params,
        )
    ).all()
    ids = [r[0] for r in rows]
    if not ids:
        return {"entries": [], "total_imported": await _count_logs(db)}

    entries = (
        await db.execute(
            select(LogEntry).where(LogEntry.id.in_(ids)).options(joinedload(LogEntry.resource).joinedload(AwsResource.customer))
        )
    ).unique().scalars().all()
    by_id = {e.id: e for e in entries}
    ordered = [by_id[i] for i in ids if i in by_id]
    return {"entries": [_log_out(e) for e in ordered], "total_imported": await _count_logs(db)}


async def _count_logs(db: AsyncSession) -> int:
    return (await db.execute(text("SELECT count(*) FROM log_entries"))).scalar_one()


# ── SSL Certificate Monitoring ──────────────────────────────────────────
# See services/cert_scan.py for the probe itself. Every real
# CustomerTenantInfo row is a monitored host — no separate model, no
# accept/review step (unlike tenant_discovery.py, there's no ambiguity to
# guard against: these are already-confirmed subdomains, not guessed
# candidates).

def _cert_row_out(t: CustomerTenantInfo) -> dict:
    return {
        "id": t.id,
        "customer_id": t.customer_id,
        "customer_name": t.customer.name if t.customer else None,
        "tier": t.customer.tier if t.customer else None,
        "environment": t.environment,
        "subdomain": t.subdomain,
        "hostname": _resolve_hostname(t.subdomain),
        "cert_expires_at": t.cert_expires_at,
        "days_until_expiry": days_until_expiry(t.cert_expires_at),
        "cert_issuer": t.cert_issuer,
        "cert_checked_at": t.cert_checked_at,
        "cert_check_error": t.cert_check_error,
        "status": cert_status(t.cert_expires_at, t.cert_check_error, t.cert_checked_at),
    }


# Worst-first, matching tenant_discovery.py's own "unmatched/worst first"
# result ordering — the whole point of this list is triaging what needs
# attention, not an alphabetical inventory.
_STATUS_ORDER = {"expired": 0, "critical": 1, "expiring": 2, "error": 3, "never_checked": 4, "valid": 5}


@router.get("/certificates")
async def list_certificates(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(CustomerTenantInfo).options(joinedload(CustomerTenantInfo.customer)))
    ).scalars().all()
    out = [_cert_row_out(t) for t in rows]
    out.sort(key=lambda r: (_STATUS_ORDER.get(r["status"], 9), r["days_until_expiry"] if r["days_until_expiry"] is not None else 999999))

    summary = {
        "total": len(out),
        "valid": sum(1 for r in out if r["status"] == "valid"),
        "expiring": sum(1 for r in out if r["status"] == "expiring"),
        "critical": sum(1 for r in out if r["status"] == "critical"),
        "expired": sum(1 for r in out if r["status"] == "expired"),
        "error": sum(1 for r in out if r["status"] == "error"),
        "never_checked": sum(1 for r in out if r["status"] == "never_checked"),
        "last_scan_at": max((r["cert_checked_at"] for r in out if r["cert_checked_at"]), default=None),
        "scan_running": is_scan_running(),
        "warn_days": CERT_WARN_DAYS,
        "critical_days": CERT_CRITICAL_DAYS,
    }
    return {"summary": summary, "rows": out}


async def _run_cert_scan_task():
    from app.services.cert_scan import scan_all_certificates

    async with AsyncSessionLocal() as db:
        result = await scan_all_certificates(db)
        db.add(AuditLog(
            actor="you", action="cert_scan.run", target_type="cert_scan", target_id="all",
            detail=f"checked={result.get('checked')} ok={result.get('ok')} errors={result.get('errors')} "
                   f"expiring={result.get('expiring_soon')} expired={result.get('expired')}",
        ))
        await db.commit()
    logger.info("Cert scan (manual trigger) finished: %s", result)


@router.post("/certificates/scan")
async def scan_certificates_now():
    """Fires the scan as a background task and returns immediately — 117+
    hosts at bounded concurrency can run well past a normal request
    timeout even though each individual handshake is fast. Check
    GET /engineering/certificates again in a minute or two (its
    summary.scan_running flag flips back to false when done) rather than
    waiting on this response — same convention as knowledge.py::extract_now()."""
    if is_scan_running():
        return {"started": False, "reason": "already running"}
    asyncio.create_task(_run_cert_scan_task())
    return {"started": True}
