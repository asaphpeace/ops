"""Deterministic supervision over the Upgrade pipeline — not an AI pass,
plain rules over real fields. Three checks:

overdue_bug_fix_upgrades(): bug/incident-driven upgrades (source +
a stale timestamp) that sit outside the user's normal Jira sys-admin-queue
attention.

unconfirmed_upgrades(): the general "no upgrade left behind" check — a
scheduled upgrade nobody has actually confirmed with DevOps or the
customer yet, even though it's imminent or already past. Real incident this
exists for: an upgrade for customer Rosco (DSD-31779) was scheduled and
completed without either party ever formally confirming, and nothing in
the app noticed.

pending_upgrades_missing_case(): a real "Pending Upgrade" ticket (a fix is
available, the customer hasn't upgraded to receive it yet) whose customer
has no active Upgrade row in the same environment to actually deliver it.
Flag only — never creates or force-relates a row. Real incident this
exists for: a one-off historical script wrongly cancelled DSD-31844 by
conflating its TEST environment with a different PROD ticket, leaving it
invisible for days until this session found and corrected it by hand. This
check is the ongoing safeguard so the next one doesn't need a manual audit
to surface."""
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.customer_tenant_info import CustomerTenantInfo
from app.models.jira_unmatched import JiraUnmatched
from app.models.upgrade import Upgrade

# Same element-wise parser as routers/releases.py::_version_tuple — kept as
# its own small copy here rather than imported, since that one lives in the
# router layer and this is a service the router imports FROM (importing the
# other way would invert the dependency).
_VERSION_NUM = re.compile(r"\d+")


def _version_tuple(v: str | None) -> tuple[int, ...] | None:
    if not v:
        return None
    parts = _VERSION_NUM.findall(v)
    return tuple(int(p) for p in parts) if parts else None


# The user's own internal upgrade-execution script requires the tenant to
# already be on 8.23 or later — confirmed directly by the user, not
# guessed. A (customer, environment) can be flagged self_serviceable in
# principle (CustomerTenantInfo.self_serviceable) yet still need real
# DevOps for a given upgrade if its currently-installed release is older
# than this baseline; the script simply doesn't work below it.
MIN_SELF_SERVICE_VERSION = (8, 23)


def _meets_min_self_service_version(release: str | None) -> bool:
    tup = _version_tuple(release)
    if tup is None:
        return False  # unknown current version -> don't assume self-service is safe
    return tup[:2] >= MIN_SELF_SERVICE_VERSION


async def effective_self_service_pairs(db: AsyncSession, customer_ids: set[int]) -> set[tuple[int, str]]:
    """Real (customer, environment) pairs that are ACTUALLY self-serviceable
    right now — flagged self_serviceable AND currently running >= 8.23.
    Below that version, DevOps has to handle it regardless of the static
    flag. Single source of truth for this check — both the Upgrade-card
    badge/DevOps-engineer-field gating (routers/upgrades.py) and
    suggested_transitions() below call this, so they can never drift onto
    two different answers for the same upgrade."""
    if not customer_ids:
        return set()
    result = await db.execute(
        select(CustomerTenantInfo.customer_id, CustomerTenantInfo.environment, CustomerTenantInfo.release).where(
            CustomerTenantInfo.customer_id.in_(customer_ids),
            CustomerTenantInfo.self_serviceable == True,  # noqa: E712
        )
    )
    return {
        (row.customer_id, row.environment)
        for row in result.all()
        if _meets_min_self_service_version(row.release)
    }

OVERDUE_DAYS = 7


async def overdue_bug_fix_upgrades(db: AsyncSession) -> list[Upgrade]:
    """Bug/Incident-fix-sourced upgrades that haven't moved in OVERDUE_DAYS.
    Staleness clock is `updated_at` (no dedicated stage-changed-at column on
    Upgrade) — a known, minor imprecision: an unrelated field edit (e.g. an
    after-hours billing note) also resets this clock. Not worth new schema
    for this pass."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=OVERDUE_DAYS)
    result = await db.execute(
        select(Upgrade)
        .where(
            Upgrade.source == "Bug/Incident fix",
            Upgrade.stage.not_in(("Verified Done", "Cancelled")),
            Upgrade.updated_at <= cutoff,
        )
        .options(joinedload(Upgrade.customer))
    )
    return result.scalars().all()


def enrich_overdue_upgrade(u: Upgrade) -> dict:
    days_stale = (datetime.now(timezone.utc) - u.updated_at).days if u.updated_at else None
    return {
        "id": u.id,
        "customer_id": u.customer_id,
        "customer_name": u.customer.name if u.customer else None,
        "customer_tier": u.customer.tier if u.customer else None,
        "jira_ref": u.jira_ref,
        "linked_vms_ref": u.linked_vms_ref,
        "stage": u.stage,
        "days_stale": days_stale,
    }


# How far ahead of a real scheduled slot this looks — a heads-up before the
# date, not just a post-mortem after it's already slipped (confirmed live:
# the Rosco/DSD-31779 incident this check exists for was scheduled for a
# date that had already passed with neither party having confirmed).
CONFIRMATION_LOOKAHEAD_DAYS = 3


async def unconfirmed_upgrades(db: AsyncSession) -> list[Upgrade]:
    """Upgrades at the Cust. Confirmed/Scheduled stage whose scheduled_at is
    imminent or already past, without BOTH devops_confirmed_at and
    customer_confirmed_at set. Confirmed live this session: 3 real rows
    match this exact pattern today (Rosco/DSD-31779, Seatrans/DSD-31856,
    Utkilen/DSD-30239) — none of them were ever flagged anywhere before
    this check existed."""
    cutoff = datetime.now(timezone.utc) + timedelta(days=CONFIRMATION_LOOKAHEAD_DAYS)
    result = await db.execute(
        select(Upgrade)
        .where(
            Upgrade.stage.in_(("Cust. Confirmed", "Scheduled")),
            Upgrade.scheduled_at.is_not(None),
            Upgrade.scheduled_at <= cutoff,
            (Upgrade.devops_confirmed_at.is_(None)) | (Upgrade.customer_confirmed_at.is_(None)),
        )
        .options(joinedload(Upgrade.customer))
    )
    return result.scalars().all()


def enrich_unconfirmed_upgrade(u: Upgrade) -> dict:
    return {
        "id": u.id,
        "customer_id": u.customer_id,
        "customer_name": u.customer.name if u.customer else None,
        "customer_tier": u.customer.tier if u.customer else None,
        "jira_ref": u.jira_ref,
        "stage": u.stage,
        "scheduled_at": u.scheduled_at,
        "devops_confirmed": u.devops_confirmed_at is not None,
        "customer_confirmed": u.customer_confirmed_at is not None,
    }


async def pending_upgrades_missing_case(db: AsyncSession) -> list[Case]:
    """Real Pending-Upgrade Cases whose customer has no active Upgrade row
    (stage not in Verified Done/Cancelled) in the same environment. One
    query for the candidate cases, one grouped query for which (customer,
    environment) pairs already have real active coverage — not N+1, even
    though there are ~50+ real Pending-Upgrade cases today across ~19
    customers. Detection only: never creates or edits an Upgrade row,
    never touches the flagged Case either — matches the user's explicit
    instruction not to force or corrupt a relation, only surface the gap."""
    cases = (
        await db.execute(
            select(Case).where(Case.raw_status == "Pending Upgrade").options(joinedload(Case.customer))
        )
    ).scalars().all()
    if not cases:
        return []

    customer_ids = {c.customer_id for c in cases}
    active_pairs_result = await db.execute(
        select(Upgrade.customer_id, Upgrade.environment).where(
            Upgrade.customer_id.in_(customer_ids),
            Upgrade.stage.not_in(("Verified Done", "Cancelled")),
        )
    )
    active_pairs = {(row.customer_id, row.environment) for row in active_pairs_result.all()}

    return [c for c in cases if (c.customer_id, c.environment) not in active_pairs]


async def suggested_transitions(db: AsyncSession) -> list[dict]:
    """Deterministic "what should move next" suggestions over the Upgrade
    pipeline — no AI, three plain rules a human approves before anything
    actually moves (see routers/upgrades.py::approve_suggestion):

    1. Self-service, skip DevOps Approval: a customer+environment the user
       can personally run (CustomerTenantInfo.self_serviceable) sitting at
       "DevOps Approval" never needs real DevOps sign-off — suggest
       advancing straight to "Cust. Confirmed".
    2. Self-service, ready to start: at "Scheduled" with the scheduled slot
       arrived and the customer confirmed — self-service needs no separate
       DevOps confirmation, only the customer's — suggest "In Progress".
    3. Non-self-service, ready to start: same as #2 but requires BOTH
       devops_confirmed_at and customer_confirmed_at (the real two-party
       gate — see unconfirmed_upgrades() above, which flags the opposite
       case: this slot arriving WITHOUT both confirmations).

    Each suggestion is recomputed fresh on every call — nothing is stored
    as "pending approval," so there's no separate state to keep in sync
    with the Upgrade row it's about (the same reasoning compute_alerts()
    already uses: detect live, never cache a verdict that could go stale)."""
    now = datetime.now(timezone.utc)
    candidates = (
        await db.execute(
            select(Upgrade)
            .where(Upgrade.stage.in_(("DevOps Approval", "Scheduled")))
            .options(joinedload(Upgrade.customer))
        )
    ).scalars().all()
    if not candidates:
        return []

    customer_ids = {u.customer_id for u in candidates}
    self_service_pairs = await effective_self_service_pairs(db, customer_ids)

    suggestions = []
    for u in candidates:
        is_self_service = (u.customer_id, u.environment) in self_service_pairs
        suggested_stage: str | None = None
        reason: str | None = None

        if u.stage == "DevOps Approval" and is_self_service:
            suggested_stage = "Cust. Confirmed"
            reason = "Self-service tenant — you can run this yourself, no DevOps sign-off needed."
        elif u.stage == "Scheduled" and u.scheduled_at is not None and u.scheduled_at <= now:
            if is_self_service and u.customer_confirmed_at is not None:
                suggested_stage = "In Progress"
                reason = "Customer confirmed and the scheduled slot has arrived — self-service, ready to start."
            elif not is_self_service and u.devops_confirmed_at is not None and u.customer_confirmed_at is not None:
                suggested_stage = "In Progress"
                reason = "DevOps and customer both confirmed, and the scheduled slot has arrived — ready to start."

        if suggested_stage:
            suggestions.append({
                "id": u.id,
                "customer_id": u.customer_id,
                "customer_name": u.customer.name if u.customer else None,
                "customer_tier": u.customer.tier if u.customer else None,
                "jira_ref": u.jira_ref,
                "environment": u.environment,
                "is_self_service": is_self_service,
                "current_stage": u.stage,
                "suggested_stage": suggested_stage,
                "reason": reason,
            })
    return suggestions


def enrich_pending_upgrade_flag(c: Case) -> dict:
    return {
        "id": c.id,
        "customer_id": c.customer_id,
        "customer_name": c.customer.name if c.customer else None,
        "customer_tier": c.customer.tier if c.customer else None,
        "jira_ref": c.jira_ref,
        "environment": c.environment,
        "linked_vms_ref": c.linked_vms_ref,
    }


async def recent_request_type_drift(db: AsyncSession) -> list[dict]:
    """Cheap, DB-only surface of what the daily
    upgrade_request_type_drift_check job (scheduler.py) most recently
    found — no live Jira call here, unlike
    jira.py::check_upgrade_request_type_drift(), which this reads the
    persisted trail of. A ~48h window survives one missed nightly run
    without going silent. Joined back against real, still-active Upgrade
    rows so a since-cancelled/resolved one doesn't linger as a stale flag."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.action == "upgrade.request_type_drift_detected",
            AuditLog.created_at >= cutoff,
        )
        .order_by(AuditLog.created_at.desc())
    )
    seen: set[str] = set()
    refs: list[tuple[str, AuditLog]] = []
    for row in result.scalars().all():
        if row.target_id in seen:
            continue
        seen.add(row.target_id)
        refs.append((row.target_id, row))
    if not refs:
        return []

    upgrades_result = await db.execute(
        select(Upgrade)
        .where(Upgrade.jira_ref.in_([ref for ref, _ in refs]), Upgrade.stage.notin_(("Verified Done", "Cancelled")))
        .options(joinedload(Upgrade.customer))
    )
    upgrades_by_ref = {u.jira_ref: u for u in upgrades_result.scalars().all()}

    out = []
    for ref, audit_row in refs:
        u = upgrades_by_ref.get(ref)
        if not u:
            continue  # already resolved/cancelled since — no longer a real flag
        # Parse the pipe-delimited detail scheduler.py wrote back into the
        # same shape jira.py::check_upgrade_request_type_drift() returns
        # live, so the frontend renders both identically.
        parts = {}
        for chunk in (audit_row.detail or "").split(" | "):
            if "=" in chunk:
                key, _, value = chunk.partition("=")
                parts[key.strip()] = value.strip()
        out.append({
            "id": u.id,
            "jira_ref": ref,
            "title": parts.get("title"),
            "customer_id": u.customer_id,
            "customer_name": u.customer.name if u.customer else None,
            "customer_tier": u.customer.tier if u.customer else None,
            "stored_request_type": parts.get("stored"),
            "live_request_type": parts.get("live"),
            "detected_at": audit_row.created_at,
        })
    return out


# Real Dataloy VMS versions confirmed live all session cluster in the major
# 2-9 range. A handful of historical Upgrade rows carry garbage to_version
# strings (e.g. "20.1", "11.1") from years of ad hoc manual entry — without
# this sanity bound, a naive tuple compare treats those as a real, very-high
# completed version and would wrongly call a real, still-open request
# "superseded." Scoped narrowly to this one check; not a drive-by fix of
# to_version data elsewhere.
def _is_sane_version(vt: tuple[int, ...] | None) -> bool:
    return vt is not None and 2 <= vt[0] <= 9


async def superseded_upgrades(db: AsyncSession) -> list[dict]:
    """Detect (never mutate) active Upgrade rows whose target version has
    already been reached or exceeded — by EITHER a different, already-
    completed Upgrade row, OR the customer's real live-synced tenant
    version (CustomerTenantInfo), for the same (customer, environment).
    The real customer need is already satisfied, whether or not this
    specific ticket was ever formally closed in Jira. Confirmed live this
    session on Spliethoff (DSD-31475 asking for a TEST upgrade DSD-31928
    already delivered) and 5 more real cases across other customers found
    via a systemic sweep, 3 of which survive the sane-version-range filter
    below (2 more only "matched" against garbage historical to_version
    strings like "20.1").

    The tenant-sync half was added after a second, distinct real incident:
    Peak People AS (DSD-31933, target 8.30.1-R) was still sitting
    "Scheduled" for a future date while their real synced PROD tenant was
    already on 8.30.3-R — reached through work never tracked as a
    completed Upgrade row in this app at all, so the completed-Upgrade-only
    check above would never have caught it. CustomerTenantInfo is the more
    authoritative source (live-probed ground truth) when it disagrees with
    this app's own tracked history — whichever source shows the higher
    real version wins.

    Pure DB query, no live Jira call — unlike
    jira.py::check_upgrade_request_type_drift(), this can run on every
    panel load with no meaningful cost."""
    active = (
        await db.execute(
            select(Upgrade).where(Upgrade.stage.notin_(("Verified Done", "Cancelled"))).options(joinedload(Upgrade.customer))
        )
    ).scalars().all()
    done = (
        await db.execute(select(Upgrade).where(Upgrade.stage == "Verified Done"))
    ).scalars().all()
    tenant_rows = (await db.execute(select(CustomerTenantInfo))).scalars().all()

    # Unify both "this need is already satisfied" sources into one shape —
    # (version_tuple, version_string, jira_ref_or_None, timestamp_or_None) —
    # keyed by (customer_id, environment), keeping whichever source shows
    # the higher real version for that pair.
    best: dict[tuple[int, str], tuple[tuple[int, ...], str, str | None, object]] = {}

    def _consider(key: tuple[int, str], vt: tuple[int, ...], version: str, jira_ref: str | None, timestamp: object) -> None:
        if key not in best or vt > best[key][0]:
            best[key] = (vt, version, jira_ref, timestamp)

    for u in done:
        vt = _version_tuple(u.to_version)
        if _is_sane_version(vt):
            _consider((u.customer_id, u.environment), vt, u.to_version, u.jira_ref, u.verified_at)
    for t in tenant_rows:
        vt = _version_tuple(t.release)
        if _is_sane_version(vt):
            _consider((t.customer_id, t.environment), vt, t.release, None, t.last_synced_at)

    superseded = []
    for u in active:
        target_vt = _version_tuple(u.to_version)
        if not _is_sane_version(target_vt):
            continue
        key = (u.customer_id, u.environment)
        if key not in best:
            continue
        done_vt, done_version, done_ref, verified_at = best[key]
        if done_vt >= target_vt:
            superseded.append({
                "id": u.id,
                "jira_ref": u.jira_ref,
                "customer_id": u.customer_id,
                "customer_name": u.customer.name if u.customer else None,
                "customer_tier": u.customer.tier if u.customer else None,
                "environment": u.environment,
                "stage": u.stage,
                "wants_version": u.to_version,
                "done_version": done_version,
                "done_jira_ref": done_ref,
                "done_verified_at": verified_at,
            })
    return superseded


async def upgrade_lineup(db: AsyncSession) -> list[dict]:
    """Real, currently-open Upgrade-Request tickets and Pending-Upgrade
    signal cases, grouped per customer, for exactly the (customer,
    environment) pairs with no active tracked Upgrade row yet. The moment
    a pair gets a real row — via the normal auto-bridge or a manual create
    — it drops out of this list on the next call; nothing here is stored,
    it's recomputed fresh every time, same reasoning as superseded_upgrades()
    above.

    Two real, distinct populations feed this, confirmed live before writing:
    - "Requests": real "Upgrade or Installation Request" tickets sitting in
      jira_unmatched (Upgrade-type tickets never become a Case — see
      services/jira.py::_ensure_upgrade_from_ticket — so an unresolved or
      already-folded one just sits here, re-upserted on every poll
      regardless of whether the auto-bridge already handled it elsewhere).
    - "Signals": real local Case rows at raw_status="Pending Upgrade" — the
      underlying defect that implies a customer probably needs to upgrade,
      independent of whether a formal request ticket exists yet.

    Connected automatically via Case.related_case_refs (real DSD-relates
    links, already captured by _extract_related_case_keys() during the
    normal poll) — no live Jira call needed here; confirmed live this
    session that 10 real signal cases already link to 6 real request
    tickets this way (e.g. DSD-30695 -> DSD-30857 for Sea Tank Chartering AS)."""
    from app.services.jira import _build_customer_match_maps, _resolve_customer_by_name_or_alias, _detect_upgrade_environment

    customers_by_id, customers_by_normalized, by_alias = await _build_customer_match_maps(db)

    active_pairs = {
        (u.customer_id, u.environment)
        for u in (await db.execute(
            select(Upgrade).where(Upgrade.stage.notin_(("Verified Done", "Cancelled")))
        )).scalars().all()
    }

    # Request side — real, resolvable, not-yet-tracked "Upgrade or
    # Installation Request" tickets. A customer name that doesn't resolve
    # is excluded here, not shown with a resolve-UI — that's Jira Mapping's
    # job, not this queue's.
    unmatched = (await db.execute(
        select(JiraUnmatched).where(JiraUnmatched.case_type == "Upgrade", JiraUnmatched.dismissed == False)  # noqa: E712
    )).scalars().all()
    requests_by_ref: dict[str, dict] = {}
    for ju in unmatched:
        customer = _resolve_customer_by_name_or_alias(ju.jira_customer_name, customers_by_normalized, by_alias, customers_by_id)
        if not customer:
            continue
        env = _detect_upgrade_environment(ju.title)
        if (customer.id, env) in active_pairs:
            continue
        requests_by_ref[ju.jira_ref] = {
            "jira_ref": ju.jira_ref, "title": ju.title, "environment": env,
            "days_open": ju.days_open, "customer_id": customer.id,
            "customer_name": customer.name, "customer_tier": customer.tier,
            "connected_signal_refs": [],
        }

    # Signal side — real Pending-Upgrade-status cases, same drop-out rule.
    pending = (await db.execute(
        select(Case).where(Case.raw_status == "Pending Upgrade").options(joinedload(Case.customer))
    )).scalars().all()
    signals_by_ref: dict[str, dict] = {}
    for c in pending:
        if not c.customer or (c.customer_id, c.environment) in active_pairs:
            continue
        connected = [r for r in (c.related_case_refs or "").split(",") if r in requests_by_ref]
        for r in connected:
            requests_by_ref[r]["connected_signal_refs"].append(c.jira_ref)
        signals_by_ref[c.jira_ref] = {
            "jira_ref": c.jira_ref, "title": c.title, "environment": c.environment,
            "days_open": c.days_open, "linked_vms_ref": c.linked_vms_ref,
            "customer_id": c.customer_id, "customer_name": c.customer.name,
            "customer_tier": c.customer.tier,
            "connected_request_ref": connected[0] if connected else None,
        }

    # Group by customer, sort messiest-first (most items) — the actual
    # "manage the chaos" ask this feature exists for.
    groups: dict[int, dict] = {}
    for item, bucket in [(r, "requests") for r in requests_by_ref.values()] + [(s, "signals") for s in signals_by_ref.values()]:
        g = groups.setdefault(item["customer_id"], {
            "customer_id": item["customer_id"], "customer_name": item["customer_name"],
            "customer_tier": item["customer_tier"], "requests": [], "signals": [],
        })
        g[bucket].append(item)

    out = list(groups.values())
    out.sort(key=lambda g: (len(g["requests"]) + len(g["signals"])), reverse=True)
    return out
