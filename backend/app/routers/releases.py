import re
import statistics
from datetime import datetime, timedelta
from typing import NamedTuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.customer import Customer
from app.models.customer_tenant_info import CustomerTenantInfo
from app.models.release import Release
from app.models.upgrade import Upgrade
from app.models.vms_bug import VmsBug
from app.schemas.release import ReleaseCreate, ReleaseOut
from app.services.bug_linkage import cases_by_bug_ref
from app.routers.desk import SUPPORT_TEAM
from app.services.jira import support_defect_dev_status, sync_release_versions_from_jira
from app.services.upgrade_supervision import overdue_bug_fix_upgrades, enrich_overdue_upgrade

router = APIRouter(prefix="/releases", tags=["releases"])

# Confirmed live: fixVersion values on DSD tickets are almost always real
# VMS release numbers (8.30.1, 8.28.2, ...) with one outlier seen (6.46.21)
# from an apparently different product — filter to the pattern actually used
# by this Release table rather than trusting every string blindly.
_VMS_VERSION = r"^\d+\.\d+(\.\d+)?$"

# Confirmed live: fixVersion presence is genuinely incomplete even at
# "PO Testing" (3/5 sampled had none) — never promise a release date for
# work that hasn't reached "Done".
_IN_PROGRESS_STATUSES = {"In Progress", "Merge Request", "PO Testing"}

_VERSION_NUM = re.compile(r"\d+")


def _version_tuple(v: str | None) -> tuple[int, ...] | None:
    """Real element-wise version comparison. The naive parseFloat(v.replace('-R',''))
    pattern used for display elsewhere (versionColor/belowLatest in
    ReleasesView.vue) is a real latent bug for two-digit minor versions —
    parseFloat("8.30") -> 8.3, which compares as LESS than 8.9. Only used for
    the new version-exposure endpoint below, not a drive-by fix of the
    existing display-only comparisons."""
    if not v:
        return None
    parts = _VERSION_NUM.findall(v)
    return tuple(int(p) for p in parts) if parts else None


@router.get("/{version}/defects")
async def release_defects(version: str, db: AsyncSession = Depends(get_db)):
    """Real defects tied to this release, via DSD fixVersion or a linked VMS bug's fixVersion.

    `Release.version` is stored with a "-R" suffix ("8.30.1-R"); `VmsBug.fix_version`
    never has one ("8.30.1") — comparing them directly was a silent no-op bug that
    made this endpoint always return zero live defects. Normalize before comparing."""
    release = (await db.execute(select(Release).where(Release.version == version))).scalar_one_or_none()

    normalized_version = version.replace("-R", "")
    bugs = (await db.execute(select(VmsBug).where(VmsBug.fix_version == normalized_version))).scalars().all()
    bug_refs = {b.jira_ref for b in bugs}

    by_bug_cases = await cases_by_bug_ref(db, bug_refs) if bug_refs else {}
    by_bug: dict[str, list[str]] = {
        ref: [c.jira_customer_name or "Unknown" for c in cases_]
        for ref, cases_ in by_bug_cases.items()
    }

    defects = [
        {
            "vms_ref": b.jira_ref,
            "status": b.status,
            "sprint_name": b.sprint_name,
            "customers": sorted(set(by_bug.get(b.jira_ref, []))),
        }
        for b in bugs
    ]
    # Multi-customer-impact bugs first — the strongest signal in this data:
    # a bug three different customers hit independently is not the same as
    # one only a single customer ever reported.
    defects.sort(key=lambda d: len(d["customers"]), reverse=True)

    return {
        "version": version,
        "curated_defects_fixed": release.defects_fixed if release else None,
        "live_defect_count": len(defects),
        "defects": defects,
    }


@router.get("/coming-next")
async def coming_next(db: AsyncSession = Depends(get_db)):
    """Bugs actively being worked, not yet Done — target release shown only when confirmed."""
    bugs = (
        (await db.execute(select(VmsBug).where(VmsBug.status.in_(_IN_PROGRESS_STATUSES))))
        .scalars()
        .all()
    )
    return [
        {
            "vms_ref": b.jira_ref,
            "status": b.status,
            "target_version": b.fix_version,
            "confirmed": b.fix_version is not None,
            "sprint_name": b.sprint_name,
            "sprint_state": b.sprint_state,
            "assignee": b.assignee,
        }
        for b in bugs
    ]


@router.get("/pending-upgrade-queue")
async def pending_upgrade_queue(db: AsyncSession = Depends(get_db)):
    """Real ex-"Pending Upgrade" cases — a fix already shipped, the customer
    hasn't upgraded to receive it yet — with their linked VMS bug(s) and
    whether a matching Release has actually been logged.

    `case_type == "Upgrade" AND status == "Closed"` is a precise, reliable
    signal for this without any schema change: sys-admin-origin Upgrade
    cases sit at status="Active" until genuinely closed, so this combination
    is only ever reached via a real Pending Upgrade ticket (confirmed live
    this session). Reuses release_defects()'s -R-suffix normalization and
    coming_next()'s confirmed/unconfirmed honesty voice — a bug can be
    status=Done with a real fix_version and still have nowhere to attach if
    no Release row for that version has been logged yet (confirmed live:
    VMS-25651/VMS-25557, both fix_version='8.32', with no '8.32' Release
    row on file)."""
    cases = (
        await db.execute(
            select(Case).where(
                Case.case_type == "Upgrade",
                Case.status == "Closed",
                Case.linked_vms_ref.isnot(None),
            )
        )
    ).scalars().all()

    if not cases:
        return []

    all_refs: set[str] = set()
    for c in cases:
        refs = (c.linked_vms_refs or c.linked_vms_ref or "").split(",")
        all_refs.update(r for r in refs if r)

    bugs_by_ref = {
        b.jira_ref: b
        for b in (await db.execute(select(VmsBug).where(VmsBug.jira_ref.in_(all_refs)))).scalars().all()
    }
    releases_by_version = {
        r.version.replace("-R", ""): r for r in (await db.execute(select(Release))).scalars().all()
    }
    customer_ids = {c.customer_id for c in cases}
    customers_by_id = {
        cu.id: cu for cu in (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars().all()
    }

    items = []
    for c in cases:
        refs = [r for r in (c.linked_vms_refs or c.linked_vms_ref or "").split(",") if r]
        customer = customers_by_id.get(c.customer_id)
        bug_list = []
        for ref in refs:
            bug = bugs_by_ref.get(ref)
            if not bug:
                continue
            matched_release = releases_by_version.get(bug.fix_version) if bug.fix_version else None
            fixed_not_released = bug.status == "Done" and bug.fix_version is not None and matched_release is None
            bug_list.append({
                "vms_ref": bug.jira_ref,
                "status": bug.status,
                "fix_version": bug.fix_version,
                "sprint_name": bug.sprint_name,
                "sprint_state": bug.sprint_state,
                "assignee": bug.assignee,
                "matched_release": matched_release.version if matched_release else None,
                "fixed_not_released": fixed_not_released,
            })
        items.append({
            "jira_ref": c.jira_ref,
            "customer_id": c.customer_id,
            "customer_name": customer.name if customer else c.jira_customer_name,
            "customer_tier": customer.tier if customer else None,
            "bugs": bug_list,
        })

    # Fixed-not-released cases first — the "aha, this is real waiting value" signal.
    items.sort(key=lambda it: not any(b["fixed_not_released"] for b in it["bugs"]))
    return items


@router.get("/defect-dev-status")
async def defect_dev_status(db: AsyncSession = Depends(get_db)):
    """Real, live cross-check of every open defect-status ticket assigned to
    the support team against its actual linked VMS dev bug — replaces the
    manual investigation this was built from (see support_defect_dev_status()'s
    own docstring in services/jira.py for the full reasoning on why this is a
    dedicated live fetch, not folded into team_open_stats() or the existing
    Pending Upgrade Queue)."""
    rows = await support_defect_dev_status(SUPPORT_TEAM)

    releases_by_version = {
        r.version.replace("-R", ""): r for r in (await db.execute(select(Release))).scalars().all()
    }

    items = []
    for row in rows:
        bug = row["bug"]
        bug_out = None
        if bug:
            matched_release = releases_by_version.get(bug["fix_version"]) if bug["fix_version"] else None
            fixed_not_released = bug["status"] == "Done" and bug["fix_version"] is not None and matched_release is None
            bug_out = {
                **bug,
                "matched_release": matched_release.version if matched_release else None,
                "fixed_not_released": fixed_not_released,
            }
        items.append({**{k: v for k, v in row.items() if k != "bug"}, "bug": bug_out})

    # Same "aha" ordering as pending_upgrade_queue: fixed-but-not-released
    # first, then unlinked-to-any-bug tickets last (the "needs a dev link"
    # signal), everything else (still being worked, no fix yet) in between.
    def _sort_key(item: dict) -> tuple[bool, bool]:
        bug = item["bug"]
        return (not (bug and bug["fixed_not_released"]), bug is None)

    items.sort(key=_sort_key)
    return items


@router.get("/bug-fix-upgrades-overdue")
async def bug_fix_upgrades_overdue(db: AsyncSession = Depends(get_db)):
    """Manually-created upgrades sourced 'Bug/Incident fix' with no stage
    movement in 7+ days — these exist specifically to unblock a real
    customer-facing bug, and sit outside the normal sys-admin-queue
    workflow, so they're the ones most likely to go unnoticed. Same shared
    helper as the My Desk Flags row card — deterministic, not AI (Jira's own
    stage/updated_at fields are all this needs)."""
    overdue = await overdue_bug_fix_upgrades(db)
    return [enrich_overdue_upgrade(u) for u in overdue]


@router.get("", response_model=list[ReleaseOut])
async def list_releases(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Release).order_by(Release.released_at.desc()))
    return result.scalars().all()


@router.get("/latest", response_model=ReleaseOut | None)
async def latest_release(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Release).where(Release.is_latest == True).order_by(Release.released_at.desc())
    )
    return result.scalar_one_or_none()


@router.post("", response_model=ReleaseOut, status_code=201)
async def create_release(data: ReleaseCreate, db: AsyncSession = Depends(get_db)):
    if data.is_latest:
        # Clear existing latest flag
        result = await db.execute(select(Release).where(Release.is_latest == True))
        for r in result.scalars().all():
            r.is_latest = False
    release = Release(**data.model_dump())
    db.add(release)
    db.add(AuditLog(
        actor="you", action="release.published", target_type="release", target_id=data.version,
        detail=f"{data.defects_fixed} defects, {data.improvements} improvements",
    ))
    await db.commit()
    await db.refresh(release)
    return release


@router.post("/sync-from-jira")
async def sync_versions_from_jira():
    """On-demand — pulls real project/VMS/versions from Jira and upserts
    Release rows for every one with a real releaseDate. Dormant/no-op if
    Jira isn't configured (matches this app's established graceful-degrade
    convention for every optional integration)."""
    return await sync_release_versions_from_jira()


@router.get("/engineer-impact")
async def engineer_impact(db: AsyncSession = Depends(get_db)):
    """Rank Dev engineers (VmsBug.assignee) by how many distinct customers
    their fixed bugs actually touch — reuses cases_by_bug_ref(), the same
    per-bug customer computation release_defects() already does, just
    rolled up per person instead of per release. No existing per-engineer
    view covers Dev work. All-time counts stay the primary ranking since
    VmsBug.jira_resolved_at only backfills real dates as each bug is
    re-synced (not instantly for every bug on this rollout) — the 90-day
    figures below are a supplementary cut, not a replacement, and will
    honestly read low/zero until sync catches up."""
    bugs = (
        await db.execute(select(VmsBug).where(VmsBug.status == "Done", VmsBug.assignee.isnot(None)))
    ).scalars().all()
    bug_refs = {b.jira_ref for b in bugs}
    by_bug_cases = await cases_by_bug_ref(db, bug_refs)
    cutoff = datetime.utcnow() - timedelta(days=90)

    by_engineer: dict[str, dict] = {}
    for b in bugs:
        entry = by_engineer.setdefault(
            b.assignee, {
                "bugs_fixed": 0, "customer_ids": set(), "top_bug": None, "top_bug_customers": 0,
                "bugs_fixed_90d": 0, "customer_ids_90d": set(),
            }
        )
        entry["bugs_fixed"] += 1
        cust_ids = {c.customer_id for c in by_bug_cases.get(b.jira_ref, [])}
        entry["customer_ids"] |= cust_ids
        if len(cust_ids) > entry["top_bug_customers"]:
            entry["top_bug_customers"] = len(cust_ids)
            entry["top_bug"] = b.jira_ref
        if b.jira_resolved_at and b.jira_resolved_at.replace(tzinfo=None) >= cutoff:
            entry["bugs_fixed_90d"] += 1
            entry["customer_ids_90d"] |= cust_ids

    result = [
        {
            "assignee": name,
            "bugs_fixed": e["bugs_fixed"],
            "customers_impacted": len(e["customer_ids"]),
            "top_bug": e["top_bug"],
            "top_bug_customers": e["top_bug_customers"],
            "bugs_fixed_90d": e["bugs_fixed_90d"],
            "customers_impacted_90d": len(e["customer_ids_90d"]),
        }
        for name, e in by_engineer.items()
    ]
    result.sort(key=lambda r: (r["customers_impacted"], r["bugs_fixed"]), reverse=True)
    return result


class _ExposurePrep(NamedTuple):
    vms_customer_ids: set[int]
    prod_rows: list[CustomerTenantInfo]
    customers_by_id: dict[int, Customer]
    releases_by_version: dict[str, Release]


async def _exposure_prep(db: AsyncSession) -> _ExposurePrep:
    """The half of version_exposure()'s computation that doesn't depend on
    which bug is being scored — run once, reused per bug (by version_exposure()
    itself, and by Troubleshoot's single-bug lookup). Customer.prod_version is
    fake seed data (only 7 real rows, no live sync path — confirmed via full
    grep, same finding as customers-below-latest). CustomerTenantInfo is the
    real source, scoped to VMS customers — same fix already applied
    everywhere else this session touched version comparisons."""
    vms_customer_ids = set(
        (await db.execute(select(Customer.id).where(Customer.product.ilike("%VMS%")))).scalars().all()
    )
    prod_rows = (
        await db.execute(select(CustomerTenantInfo).where(
            CustomerTenantInfo.environment == "PROD",
            CustomerTenantInfo.customer_id.in_(vms_customer_ids),
        ))
    ).scalars().all() if vms_customer_ids else []
    customers_by_id = {
        c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(vms_customer_ids)))).scalars().all()
    } if vms_customer_ids else {}
    releases_by_version = {
        r.version.replace("-R", ""): r for r in (await db.execute(select(Release))).scalars().all()
    }
    return _ExposurePrep(vms_customer_ids, prod_rows, customers_by_id, releases_by_version)


def _exposure_for_bug(bug: VmsBug, reported: list[Case], prep: _ExposurePrep) -> dict:
    """Per-bug half of version_exposure()'s computation: reported vs.
    silently-exposed customers, and whether a matching Release is logged.
    Lifted verbatim out of that endpoint's own loop body so a single-bug
    lookup (Troubleshoot) reuses the exact same logic instead of a second,
    driftable copy."""
    fix_tuple = _version_tuple(bug.fix_version)
    reported_ids = {c.customer_id for c in reported}
    reported_by_id: dict[int, dict] = {}
    for c in reported:
        reported_by_id[c.customer_id] = {
            "id": c.customer_id,
            "name": c.jira_customer_name or (c.customer.name if c.customer else "Unknown"),
            "tier": c.customer.tier if c.customer else None,
        }
    reported_out = sorted(reported_by_id.values(), key=lambda x: x["name"])

    silently_exposed = []
    if fix_tuple:
        for row in prep.prod_rows:
            if not row.release or row.customer_id in reported_ids:
                continue
            row_tuple = _version_tuple(row.release)
            if row_tuple and row_tuple < fix_tuple:
                cust = prep.customers_by_id.get(row.customer_id)
                if not cust:
                    continue
                silently_exposed.append({
                    "id": cust.id, "name": cust.name, "tier": cust.tier, "prod_version": row.release,
                })

    matched_release = prep.releases_by_version.get(bug.fix_version)
    return {
        "vms_ref": bug.jira_ref,
        "fix_version": bug.fix_version,
        "assignee": bug.assignee,
        "sprint_name": bug.sprint_name,
        "matched_release": matched_release.version if matched_release else None,
        "reported_customers": reported_out,
        "silently_exposed_customers": sorted(silently_exposed, key=lambda x: x["name"]),
    }


@router.get("/version-exposure")
async def version_exposure(db: AsyncSession = Depends(get_db)):
    """Fleet-wide: for each real, reported, fixed defect, who's still running
    a version behind the fix — whether or not they ever opened a ticket for
    it. Reported customers come from cases_by_bug_ref(); "silently exposed"
    customers are found by comparing real CustomerTenantInfo PROD versions
    (scoped to VMS customers) against VmsBug.fix_version, independent of
    whether they ever complained — the actual fleet-safety signal, broader
    than pending_upgrade_queue's Upgrade-ticket-origin slice (which only
    covers customers who already went through the Pending-Upgrade workflow).
    Previously read the fake Customer.prod_version field across all
    customers (only 7 real seeded rows, no live sync path, no VMS scoping)
    — fixed to match customers-below-latest's real data source."""
    bugs = (
        await db.execute(select(VmsBug).where(VmsBug.status == "Done", VmsBug.fix_version.isnot(None)))
    ).scalars().all()
    bug_refs = {b.jira_ref for b in bugs}
    by_bug_cases = await cases_by_bug_ref(db, bug_refs)
    # Only real, reported defects — a Task/Story fix nobody ever complained
    # about isn't "exposure" in any customer-facing sense.
    bugs = [b for b in bugs if by_bug_cases.get(b.jira_ref)]

    prep = await _exposure_prep(db)
    items = [_exposure_for_bug(b, by_bug_cases.get(b.jira_ref, []), prep) for b in bugs]
    items.sort(key=lambda it: len(it["silently_exposed_customers"]), reverse=True)
    return items


@router.get("/missing")
async def missing_releases(db: AsyncSession = Depends(get_db)):
    """Real fix_versions with real, reported, fixed defects but no logged
    Release row. Only 3 Release rows exist against dozens of real fix
    versions in the wild (confirmed via version_exposure's live output) —
    that's a data-entry gap, not a missing-intelligence one, and the app
    already has everything needed to detect it and nudge someone to close it."""
    bugs = (
        await db.execute(select(VmsBug).where(VmsBug.status == "Done", VmsBug.fix_version.isnot(None)))
    ).scalars().all()
    bug_refs = {b.jira_ref for b in bugs}
    by_bug_cases = await cases_by_bug_ref(db, bug_refs)
    releases_by_version = {
        r.version.replace("-R", ""): r for r in (await db.execute(select(Release))).scalars().all()
    }

    by_version: dict[str, dict] = {}
    for b in bugs:
        if not by_bug_cases.get(b.jira_ref):
            continue  # only real, reported defects — same quality bar as version_exposure
        if b.fix_version in releases_by_version:
            continue  # already logged
        entry = by_version.setdefault(b.fix_version, {"bugs": [], "customer_ids": set()})
        entry["bugs"].append(b)
        entry["customer_ids"] |= {c.customer_id for c in by_bug_cases[b.jira_ref]}

    result = [
        {
            "fix_version": v,
            "bug_count": len(e["bugs"]),
            "customer_count": len(e["customer_ids"]),
            "bugs": [
                {"vms_ref": b.jira_ref, "status": b.status, "sprint_name": b.sprint_name, "assignee": b.assignee}
                for b in e["bugs"]
            ],
        }
        for v, e in by_version.items()
    ]
    result.sort(key=lambda r: r["customer_count"], reverse=True)
    return result


@router.get("/fix-to-relief")
async def fix_to_relief(db: AsyncSession = Depends(get_db)):
    """How long, in the real world, does it take between a customer
    reporting a problem and that customer actually receiving the fix?
    Anchors on Case.created_at (Jira-authoritative) rather than any VmsBug
    fix timestamp — VmsBug has no reliable per-bug "fixed at" moment even
    with jira_resolved_at now synced (that's the bug's own resolution, not
    when the *customer* got relief) — and this has the honesty advantage of
    spanning the WHOLE workflow (dev time + release logging + scheduling),
    not just dev velocity. still_waiting_count is supporting context only —
    pending_upgrade_queue/version_exposure remain the actionable queues."""
    bugs = (
        await db.execute(select(VmsBug).where(VmsBug.status == "Done", VmsBug.fix_version.isnot(None)))
    ).scalars().all()
    bug_by_ref = {b.jira_ref: b for b in bugs}
    bug_refs = set(bug_by_ref)
    by_bug_cases = await cases_by_bug_ref(db, bug_refs)

    upgrades = (
        await db.execute(select(Upgrade).where(Upgrade.stage == "Verified Done", Upgrade.verified_at.isnot(None)))
    ).scalars().all()
    upgrades_by_customer: dict[int, list[Upgrade]] = {}
    for u in upgrades:
        upgrades_by_customer.setdefault(u.customer_id, []).append(u)

    resolved = []
    still_waiting = 0
    for ref, cases in by_bug_cases.items():
        bug = bug_by_ref.get(ref)
        if not bug:
            continue
        fix_tuple = _version_tuple(bug.fix_version)
        if not fix_tuple:
            continue
        for c in cases:
            candidates = [
                u for u in upgrades_by_customer.get(c.customer_id, [])
                if u.verified_at and u.verified_at >= c.created_at
                and _version_tuple(u.to_version) and _version_tuple(u.to_version) >= fix_tuple
            ]
            if candidates:
                relief = min(candidates, key=lambda u: u.verified_at)
                days = (relief.verified_at - c.created_at).days
                resolved.append({
                    "jira_ref": c.jira_ref,
                    "vms_ref": ref,
                    "customer_name": c.jira_customer_name or (c.customer.name if c.customer else "Unknown"),
                    "reported_at": c.created_at,
                    "relieved_at": relief.verified_at,
                    "days": days,
                })
            else:
                still_waiting += 1

    days_list = [r["days"] for r in resolved]
    median_days = statistics.median(days_list) if days_list else None
    mean_days = round(statistics.mean(days_list), 1) if days_list else None

    resolved.sort(key=lambda r: r["days"], reverse=True)
    return {
        "median_days": median_days,
        "mean_days": mean_days,
        "resolved_count": len(resolved),
        "still_waiting_count": still_waiting,
        "cases": resolved,
    }


@router.get("/customers-below-latest")
async def customers_below_latest(db: AsyncSession = Depends(get_db)):
    """Real "who's behind" data. Customer.prod_version is fake seed data —
    set only in seed.py for 7 hand-seeded customers, touched by no sync path
    anywhere (confirmed via full grep). CustomerTenantInfo is the actual
    source of truth (real, live-probed per customer/environment via the
    per-customer "Sync" action) but still only covers a fraction of
    customers — there's no way to backfill that without real subdomain data
    entry, so this honestly reports how many customers have no version on
    file at all rather than pretending completeness. Uses _version_tuple —
    real CustomerTenantInfo values include single-digit-minor versions like
    "8.9.3-R" that the naive parseFloat comparison used elsewhere gets
    backwards.

    `no_data_count` is scoped to real VMS customers (product ILIKE '%VMS%'),
    not the full customer base — confirmed live this same denominator bug
    on Customer Intelligence's own stat strip: most of the ~576 total
    customers are Email/CompassAir-only accounts with no real AWS/VMS
    infrastructure at all, so counting them as "missing version data" would
    be honestly meaningless (they were never expected to have any)."""
    latest = (await db.execute(select(Release).where(Release.is_latest == True))).scalar_one_or_none()  # noqa: E712
    if not latest:
        return {"latest_version": None, "customers": [], "no_data_count": 0}
    latest_tuple = _version_tuple(latest.version)

    prod_rows = (
        await db.execute(select(CustomerTenantInfo).where(CustomerTenantInfo.environment == "PROD"))
    ).scalars().all()

    vms_customer_ids = set(
        (await db.execute(select(Customer.id).where(Customer.product.ilike("%VMS%")))).scalars().all()
    )
    known_customer_ids = {r.customer_id for r in prod_rows if r.release and r.customer_id in vms_customer_ids}
    no_data_count = len(vms_customer_ids) - len(known_customer_ids)

    customers_by_id = {
        c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(known_customer_ids)))).scalars().all()
    } if known_customer_ids else {}

    below = []
    for row in prod_rows:
        if not row.release or not latest_tuple:
            continue
        row_tuple = _version_tuple(row.release)
        if row_tuple and row_tuple < latest_tuple:
            cust = customers_by_id.get(row.customer_id)
            if not cust:
                continue
            below.append({
                "id": cust.id,
                "name": cust.name,
                "tier": cust.tier,
                "prod_version": row.release,
                "renewal_date": cust.renewal_date,
            })

    below.sort(key=lambda c: c["name"])
    return {"latest_version": latest.version, "customers": below, "no_data_count": no_data_count}


# Minor-version-range buckets, tested against a real (major, minor, patch)
# tuple from _version_tuple — not the old TrendsView.vue chart's naive
# parseFloat("8.9.3-R".replace('-R','')) = 8.9, which numerically outranks
# parseFloat("8.30.1-R") = 8.3 and would sort a genuinely OLDER release as
# newer than the current latest. Ordered first-match-wins, most recent first.
_DIST_BUCKETS = [
    ("8.30+", "v-new", lambda t: t[1] >= 30),
    ("8.28–29", "v-new", lambda t: 28 <= t[1] <= 29),
    ("8.25–27", "v-mid", lambda t: 25 <= t[1] <= 27),
    ("8.23–24", "v-mid", lambda t: 23 <= t[1] <= 24),
    ("8.17–22", "v-old", lambda t: 17 <= t[1] <= 22),
    ("< 8.17", "v-old", lambda t: t[1] < 17),
]


@router.get("/version-distribution")
async def version_distribution(db: AsyncSession = Depends(get_db)):
    """Real VMS-fleet version spread — replaces TrendsView.vue's old chart,
    which read Customer.prod_version (fake seed data, only 7 real rows, no
    live sync path — confirmed via full grep) across ALL customers with a
    naive parseFloat comparator. This uses CustomerTenantInfo (the real,
    though still sparse, source — same fix already applied to
    customers-below-latest) via _version_tuple's proper major/minor
    comparison, scoped to real VMS customers only. Customers with no known
    PROD version are reported as their own honest "Unknown" bucket rather
    than silently dropped, matching customers-below-latest's no_data_count
    convention."""
    vms_customer_ids = set(
        (await db.execute(select(Customer.id).where(Customer.product.ilike("%VMS%")))).scalars().all()
    )
    prod_rows = (
        await db.execute(select(CustomerTenantInfo).where(
            CustomerTenantInfo.environment == "PROD",
            CustomerTenantInfo.customer_id.in_(vms_customer_ids),
        ))
    ).scalars().all() if vms_customer_ids else []

    known_ids: set[int] = set()
    bucket_counts = {label: 0 for label, _cls, _test in _DIST_BUCKETS}
    for row in prod_rows:
        if not row.release:
            continue
        v_tuple = _version_tuple(row.release)
        if not v_tuple or len(v_tuple) < 2:
            continue
        known_ids.add(row.customer_id)
        for label, _cls, test in _DIST_BUCKETS:
            if test(v_tuple):
                bucket_counts[label] += 1
                break

    total = len(vms_customer_ids) or 1
    buckets = [
        {"label": label, "cls": cls, "count": bucket_counts[label], "pct": round(bucket_counts[label] / total * 100)}
        for label, cls, _test in _DIST_BUCKETS
        if bucket_counts[label] > 0
    ]
    unknown_count = len(vms_customer_ids) - len(known_ids)
    if unknown_count > 0:
        buckets.append({"label": "Unknown", "cls": "v-unknown", "count": unknown_count, "pct": round(unknown_count / total * 100)})

    return {"vms_customer_count": len(vms_customer_ids), "buckets": buckets}
