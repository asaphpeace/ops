from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import settings
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.upgrade import Upgrade
from app.models.customer import Customer
from app.models.customer_name_alias import CustomerNameAlias
from app.models.customer_tenant_info import CustomerTenantInfo
from app.models.unmatched_upgrade_customer import UnmatchedUpgradeCustomer
from app.schemas.upgrade import UpgradeCreate, UpgradeUpdate, UpgradeOut
from app.services.jira import _SYS_ADMIN_REQUEST_TYPE, check_upgrade_request_type_drift
from app.services.upgrade_supervision import effective_self_service_pairs, recent_request_type_drift, suggested_transitions, superseded_upgrades, upgrade_lineup

router = APIRouter(prefix="/upgrades", tags=["upgrades"])

PIPELINE_STAGES = [
    "Requested",
    "DevOps Approval",
    "Cust. Confirmed",
    "Scheduled",
    "In Progress",
    "Verified Done",
]

# The only two real DevOps engineers who ever handle a non-self-service
# upgrade — same roster as lanes.py's DEVOPS_ROSTER, kept as a plain literal
# here rather than imported to avoid a services-layer -> router import.
DEVOPS_ENGINEERS = ("Martin Fure", "Elias Hjellestad")


async def _self_service_pairs(db: AsyncSession, customer_ids: set[int]) -> set[tuple[int, str]]:
    # Delegates to the service layer's effective_self_service_pairs() — the
    # single source of truth for "actually self-serviceable right now"
    # (flagged self_serviceable AND currently running >= 8.23, the user's
    # script's real version floor). suggested_transitions() uses the exact
    # same function, so the card badge/DevOps-engineer gating here and the
    # suggestion logic can never disagree about the same upgrade.
    return await effective_self_service_pairs(db, customer_ids)


def _enrich(
    u: Upgrade,
    self_service_pairs: set[tuple[int, str]] | None = None,
    tenant_versions: dict[tuple[int, str], tuple[str, object]] | None = None,
) -> dict:
    d = {col.name: getattr(u, col.name) for col in u.__table__.columns}
    if u.customer:
        d["customer_name"] = u.customer.name
        d["customer_tier"] = u.customer.tier
    if self_service_pairs is not None:
        d["is_self_service"] = (u.customer_id, u.environment) in self_service_pairs
    # Real, live-synced version for this customer+environment right now —
    # deliberately separate from to_version (this ticket's recorded
    # target, which can be stale/"Unknown" for older or badly-parsed
    # tickets). Only attached where tenant_versions is passed (the
    # Verified Done history bucket, where "what are they actually on now"
    # is the useful question) — never backfilled onto to_version itself,
    # since that would misrepresent this specific ticket's real target.
    if tenant_versions is not None:
        found = tenant_versions.get((u.customer_id, u.environment))
        d["current_version"] = found[0] if found else None
        d["current_version_synced_at"] = found[1] if found else None
    return d


@router.post("/sync-from-jira")
async def sync_from_jira():
    """On-demand — real completed upgrades, via the durable 'PROD Upgrade' /
    'TEST / DEV Upgrade' Jira components on resolved tickets. Never scheduled;
    this is a full-history scan, heavier than the regular 5-minute poll."""
    from app.services.jira import sync_completed_upgrades
    return await sync_completed_upgrades()


@router.get("/request-type-drift")
async def request_type_drift():
    """On-demand — real-time re-check of every active, sys-admin-classified
    Upgrade row's linked ticket against its current live Jira request_type.
    Detection only, never mutates anything; see
    services/jira.py::check_upgrade_request_type_drift() for the full
    reasoning and the real incidents (DSD-30760) this exists for."""
    return {"drifted": await check_upgrade_request_type_drift()}


@router.get("/request-type-drift/recent")
async def request_type_drift_recent(db: AsyncSession = Depends(get_db)):
    """Cheap, DB-only — what the daily scheduled check most recently found
    (see scheduler.py::_upgrade_request_type_drift_check), no live Jira
    call. Lets the Operations > Upgrades panel show yesterday's finding on
    page load without hitting Jira every time; "Check for drift" still
    triggers a fresh, on-demand live re-check via the endpoint above."""
    return {"drifted": await recent_request_type_drift(db)}


@router.get("/superseded")
async def superseded(db: AsyncSession = Depends(get_db)):
    """Detection only, no live Jira call needed — see
    services/upgrade_supervision.py::superseded_upgrades() for the full
    reasoning and the real cases (Spliethoff DSD-31475/DSD-31928, plus
    others) this exists for."""
    return {"superseded": await superseded_upgrades(db)}


@router.get("/lineup")
async def lineup(db: AsyncSession = Depends(get_db)):
    """Real requests + Pending-Upgrade signals not yet tracked as one
    active Upgrade row, grouped by customer — see
    services/upgrade_supervision.py::upgrade_lineup() for the full
    reasoning. Pure DB query, no live Jira call."""
    return await upgrade_lineup(db)


@router.get("/unmatched-customers")
async def list_unmatched_customers(db: AsyncSession = Depends(get_db)):
    """Real customer-name strings from Jira upgrade tickets that didn't match
    any local Customer — same resolution pattern as Jira Mapping for cases:
    a human assigns to an existing customer, creates a new one, or dismisses."""
    result = await db.execute(
        select(UnmatchedUpgradeCustomer)
        .where(UnmatchedUpgradeCustomer.dismissed == False)  # noqa: E712
        .order_by(UnmatchedUpgradeCustomer.ticket_count.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "customer_name": r.customer_name,
            "ticket_count": r.ticket_count,
            "sample_jira_refs": r.sample_jira_refs.split(",") if r.sample_jira_refs else [],
            "first_seen_at": r.first_seen_at,
            "last_seen_at": r.last_seen_at,
        }
        for r in rows
    ]


@router.post("/unmatched-customers/{unmatched_id}/assign")
async def assign_unmatched_customer(unmatched_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    """Link this exact Jira customer-name string to an existing local
    customer via a durable alias — never renames the existing customer's
    real name to match one ticket's string."""
    from app.services.jira import sync_completed_upgrades

    customer_id = data.get("customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required")

    row = (await db.execute(
        select(UnmatchedUpgradeCustomer).where(UnmatchedUpgradeCustomer.id == unmatched_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Unmatched customer not found")

    customer = (await db.execute(select(Customer).where(Customer.id == customer_id))).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    existing_alias = (await db.execute(
        select(CustomerNameAlias).where(CustomerNameAlias.alias_name == row.customer_name)
    )).scalar_one_or_none()
    if existing_alias:
        existing_alias.customer_id = customer_id
    else:
        db.add(CustomerNameAlias(customer_id=customer_id, alias_name=row.customer_name))
    row.dismissed = True
    await db.commit()

    return await sync_completed_upgrades()


@router.post("/unmatched-customers/{unmatched_id}/create-customer")
async def create_customer_from_unmatched(unmatched_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    """Create a brand-new customer named exactly as Jira has it, so future
    syncs match by plain exact name — no alias needed for this path."""
    from app.services.jira import sync_completed_upgrades
    from app.routers.customers import TIER_UPGRADE_LIMITS

    row = (await db.execute(
        select(UnmatchedUpgradeCustomer).where(UnmatchedUpgradeCustomer.id == unmatched_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Unmatched customer not found")

    tier = data.get("tier") or "Scale"
    customer = Customer(
        name=row.customer_name,
        tier=tier,
        csm=data.get("csm") or "Unassigned",
        upgrades_limit=TIER_UPGRADE_LIMITS.get(tier, 4),
    )
    db.add(customer)
    row.dismissed = True
    await db.commit()

    return await sync_completed_upgrades()


@router.post("/unmatched-customers/{unmatched_id}/dismiss")
async def dismiss_unmatched_customer(unmatched_id: int, db: AsyncSession = Depends(get_db)):
    """For junk/non-company values (Jira placeholders, internal test data,
    vessel codes) — never resurfaces once dismissed."""
    row = (await db.execute(
        select(UnmatchedUpgradeCustomer).where(UnmatchedUpgradeCustomer.id == unmatched_id)
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Unmatched customer not found")
    row.dismissed = True
    await db.commit()
    return {"status": "dismissed"}


@router.get("", response_model=list[UpgradeOut])
async def list_upgrades(
    stage: str | None = None,
    customer_id: int | None = None,
    blocked: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Upgrade).options(joinedload(Upgrade.customer))
    if stage:
        q = q.where(Upgrade.stage == stage)
    if customer_id:
        q = q.where(Upgrade.customer_id == customer_id)
    if blocked is not None:
        q = q.where(Upgrade.blocked == blocked)
    q = q.order_by(Upgrade.created_at.desc())
    result = await db.execute(q)
    rows = result.scalars().all()
    pairs = await _self_service_pairs(db, {u.customer_id for u in rows})
    return [UpgradeOut(**_enrich(u, pairs)) for u in rows]


@router.get("/pipeline")
async def pipeline_summary(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Upgrade)
        .where(Upgrade.stage != "Verified Done")
        .options(joinedload(Upgrade.customer))
    )
    all_upgrades = result.scalars().all()

    # Only a genuine "Upgrade or Installation Request" ticket puts a
    # customer on this board — confirmed live this session that _map_type()
    # collapses BOTH that request type AND a "Pending Upgrade"-status ticket
    # into the same local case_type="Upgrade", so case_type alone can't
    # distinguish them. A Pending Upgrade case never belongs here by
    # itself; it needs its own separate, real Upgrade-or-Installation-
    # Request case (see services/upgrade_supervision.py::pending_upgrades_
    # missing_case, which flags exactly the customers this excludes).
    #
    # This reads Upgrade.request_type directly (captured once at creation
    # time in _ensure_upgrade_from_ticket()) rather than cross-referencing a
    # local Case row — confirmed live this never worked for genuine
    # sys-admin upgrades: Case creation is deliberately skipped for
    # Upgrade-classified tickets (they go straight to the Upgrade pipeline),
    # so a Case-based cross-reference could only ever see a request_type for
    # tickets that happen to already have an (unrelated) local Case row —
    # which silently hid every real, newly-created sys-admin upgrade from
    # this exact board. Rows with no jira_ref at all (a manual entry or a
    # Release Intelligence recommendation with no real ticket behind it)
    # are excluded too, per explicit instruction — this board only shows
    # upgrades backed by a real case. Rows
    # created before this column existed have request_type=None and are
    # excluded until backfilled/re-synced — consistent with how this
    # session already relegated the historical Pending-Upgrade-sourced
    # population to the Releases > Pending Upgrade Queue instead.
    # Confirmed live: this initial query only excludes "Verified Done", not
    # "Cancelled" — a Cancelled row can still pass the jira_ref/request_type
    # check above (e.g. one of Klaveness/Stena's real duplicate-cleanup
    # cancellations, which carries a genuine sys-admin request_type), so it
    # was silently inflating active_total/done-count math above what the
    # board actually renders: by_stage only has keys for the 6 real
    # PIPELINE_STAGES, never "Cancelled," so these rows counted in the
    # total but appeared in zero visible columns — a real mismatch, caught
    # once the stats row became drillable and its own count didn't match
    # what the drill-down actually listed.
    upgrades = [
        u for u in all_upgrades
        if u.stage != "Cancelled" and u.jira_ref and u.request_type == _SYS_ADMIN_REQUEST_TYPE
    ]

    pairs = await _self_service_pairs(db, {u.customer_id for u in all_upgrades})

    by_stage: dict[str, list] = {s: [] for s in PIPELINE_STAGES}
    for u in upgrades:
        if u.stage in by_stage:
            by_stage[u.stage].append(_enrich(u, pairs))

    blocked_count = sum(1 for u in upgrades if u.blocked)
    # confirmed_at is a dead field (nothing in the live write path ever sets
    # it) — real confirmation now lives in devops_confirmed_at/
    # customer_confirmed_at (see services/upgrade_supervision.py).
    unconfirmed = sum(
        1 for u in upgrades
        if u.stage in ("Cust. Confirmed", "Scheduled") and not (u.devops_confirmed_at and u.customer_confirmed_at)
    )

    # "Verified Done" is deliberately excluded from the query above (it's
    # not an active stage), but the board still renders a Verified Done
    # column — without this, that column is structurally guaranteed to
    # always be empty regardless of how many upgrades actually complete.
    #
    # The History table's own list is scoped to a rolling 30 days, NOT
    # calendar-month-to-date — confirmed live this matters: a hard
    # month_start boundary meant every completion from the day before a
    # month rolled over (e.g. Aug 31 upgrades, checked on Sept 1) vanished
    # from the table entirely, even though they were completed yesterday.
    # done_this_month (the stat tile) keeps its own real calendar-month
    # query separately below — that label means "this month," so it must
    # stay month-scoped even though the table beneath it now shows more.
    history_cutoff = datetime.utcnow() - timedelta(days=30)
    history_result = await db.execute(
        select(Upgrade)
        .where(
            Upgrade.stage == "Verified Done",
            Upgrade.verified_at.is_not(None),
            Upgrade.verified_at >= history_cutoff,
        )
        .options(joinedload(Upgrade.customer))
    )
    history_upgrades = history_result.scalars().all()
    history_pairs = await _self_service_pairs(db, {u.customer_id for u in history_upgrades})

    tenant_result = await db.execute(
        select(CustomerTenantInfo).where(
            CustomerTenantInfo.customer_id.in_({u.customer_id for u in history_upgrades})
        )
    )
    tenant_versions = {
        (t.customer_id, t.environment): (t.release, t.last_synced_at)
        for t in tenant_result.scalars().all()
        if t.release
    }
    by_stage["Verified Done"] = [_enrich(u, history_pairs, tenant_versions) for u in history_upgrades]

    month_start = date.today().replace(day=1)
    done_this_month_count = sum(1 for u in history_upgrades if u.verified_at and u.verified_at.date() >= month_start)

    return {
        "stages": by_stage,
        "active_total": len(upgrades),
        "blocked": blocked_count,
        "unconfirmed_slots": unconfirmed,
        "done_this_month": done_this_month_count,
        "devops_slots_per_week": settings.devops_slots_per_week,
    }


@router.post("", response_model=UpgradeOut, status_code=201)
async def create_upgrade(data: UpgradeCreate, db: AsyncSession = Depends(get_db)):
    # Real dedup gap, closed here: this endpoint used to insert
    # unconditionally, unlike _ensure_upgrade_from_ticket() (services/jira.py),
    # which already checks customer+environment before creating a row.
    # Confirmed live this session that skipping this check is a real
    # problem, not a hypothetical one — 11 customers had 2-10 duplicate
    # active upgrade rows before a one-off cleanup earlier this session.
    # This endpoint is also what "Recommend Upgrade" on Release Intelligence
    # calls, so it needs the same guard. A human is waiting on this
    # response, so a real 409 naming the existing row beats a silent no-op.
    existing = (await db.execute(
        select(Upgrade).where(
            Upgrade.customer_id == data.customer_id,
            Upgrade.environment == data.environment,
            Upgrade.stage.not_in(("Verified Done", "Cancelled")),
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"{existing.jira_ref or 'This customer'} already has an active {data.environment} upgrade "
                   f"(stage: {existing.stage}) — not creating a duplicate.",
        )

    upgrade = Upgrade(**data.model_dump())
    db.add(upgrade)
    await db.flush()
    db.add(AuditLog(actor="you", action="upgrade.created", target_type="customer", target_id=str(data.customer_id)))
    await db.commit()
    result = await db.execute(
        select(Upgrade).where(Upgrade.id == upgrade.id).options(joinedload(Upgrade.customer))
    )
    u = result.scalar_one()
    pairs = await _self_service_pairs(db, {u.customer_id})
    return UpgradeOut(**_enrich(u, pairs))


@router.patch("/{upgrade_id}", response_model=UpgradeOut)
async def update_upgrade(upgrade_id: int, data: UpgradeUpdate, db: AsyncSession = Depends(get_db)):
    from app.services.calendar import upsert_upgrade_event, cancel_upgrade_event

    result = await db.execute(
        select(Upgrade).where(Upgrade.id == upgrade_id).options(joinedload(Upgrade.customer))
    )
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Upgrade not found")

    payload = data.model_dump(exclude_none=True)
    cancel_slot = payload.pop("cancel_slot", None)

    if payload.get("devops_engineer") and payload["devops_engineer"] not in DEVOPS_ENGINEERS:
        raise HTTPException(
            status_code=400,
            detail=f"devops_engineer must be one of {DEVOPS_ENGINEERS}, got {payload['devops_engineer']!r}",
        )

    # Capture before overwriting — a real confirmation event (None -> a real
    # timestamp) gets its own AuditLog row, same as every other tracked
    # transition in this app (case.status_changed, bug.status_changed, etc).
    newly_devops_confirmed = u.devops_confirmed_at is None and payload.get("devops_confirmed_at") is not None
    newly_customer_confirmed = u.customer_confirmed_at is None and payload.get("customer_confirmed_at") is not None

    for key, value in payload.items():
        setattr(u, key, value)

    if newly_devops_confirmed:
        db.add(AuditLog(actor="you", action="upgrade.devops_confirmed", target_type="upgrade", target_id=u.jira_ref or str(u.id)))
    if newly_customer_confirmed:
        db.add(AuditLog(actor="you", action="upgrade.customer_confirmed", target_type="upgrade", target_id=u.jira_ref or str(u.id)))

    # A plain "→ Verified Done" stage-advance never sends verified_at/
    # date_done — without stamping them here, the completion is silently
    # unrecorded: done_this_month can never count it, and the Verified
    # Done column above has nothing to show. Only stamp when the caller
    # didn't already supply a real value (e.g. a Jira-driven sync setting
    # its own authoritative date_done).
    if payload.get("stage") == "Verified Done":
        now = datetime.utcnow()
        if u.verified_at is None:
            u.verified_at = now
        if u.date_done is None:
            u.date_done = now

    if cancel_slot:
        await cancel_upgrade_event(u)
        u.scheduled_at = None
        u.google_event_id = None
    elif "scheduled_at" in payload and u.scheduled_at:
        customer_name = u.customer.name if u.customer else "Unknown"
        event_id = await upsert_upgrade_event(u, customer_name)
        if event_id:
            u.google_event_id = event_id

    # Recomputed (not incremented) so re-syncs / repeat PATCHes on the same
    # row can never drift or double-count — mirrors how upgrades_used is
    # recomputed from source rows in sync_completed_upgrades() rather than
    # bumped in place. After-hours has no Jira signal, so this is the only
    # place it can live.
    if u.after_hours and u.stage == "Verified Done" and u.customer:
        count_result = await db.execute(
            select(Upgrade).where(
                Upgrade.customer_id == u.customer_id,
                Upgrade.after_hours == True,  # noqa: E712
                Upgrade.stage == "Verified Done",
            )
        )
        u.customer.after_hours_used = len(count_result.scalars().all())

    await db.commit()
    await db.refresh(u)
    pairs = await _self_service_pairs(db, {u.customer_id})
    return UpgradeOut(**_enrich(u, pairs))


@router.get("/suggestions")
async def get_suggestions(db: AsyncSession = Depends(get_db)):
    """Deterministic pipeline-transition suggestions — see
    services/upgrade_supervision.py::suggested_transitions() for the three
    rules. Recomputed fresh on every call, nothing stored."""
    return {"suggestions": await suggested_transitions(db)}


@router.post("/{upgrade_id}/approve-suggestion", response_model=UpgradeOut)
async def approve_suggestion(upgrade_id: int, db: AsyncSession = Depends(get_db)):
    """The one real mutation this supervisor can trigger, and only on an
    explicit human click — recomputes the suggestion for this specific
    upgrade server-side (never trusts a stage the client might have cached)
    and applies it. 400 if nothing is actually suggested right now (the
    state moved since the client last saw it)."""
    result = await db.execute(
        select(Upgrade).where(Upgrade.id == upgrade_id).options(joinedload(Upgrade.customer))
    )
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Upgrade not found")

    current = next((s for s in await suggested_transitions(db) if s["id"] == upgrade_id), None)
    if not current:
        raise HTTPException(status_code=400, detail="No suggestion is currently pending for this upgrade.")

    from_stage = u.stage
    u.stage = current["suggested_stage"]
    db.add(AuditLog(
        actor="you", action="upgrade.suggestion_approved", target_type="upgrade", target_id=u.jira_ref or str(u.id),
        detail=f"{from_stage} -> {current['suggested_stage']} ({current['reason']})",
    ))
    await db.commit()
    await db.refresh(u)
    pairs = await _self_service_pairs(db, {u.customer_id})
    return UpgradeOut(**_enrich(u, pairs))


# ── Live Jira state for the pipeline board ───────────────────────────────
# The board shows every active "Upgrade or Installation Request" row, but
# rows are created once from a ticket and the local Case cache doesn't hold
# most sys-admin tickets — so a ticket resolved or reassigned in Jira kept
# sitting on the board (confirmed live: DSD-32219 resolved, still
# "Requested"). The board's "My open upgrade tickets" view filters on this
# live state instead: still open in Jira AND assigned to YOU.
_JIRA_STATE_TTL = 300
_jira_state_cache: dict = {"refs": None, "at": 0.0, "data": None}


@router.get("/pipeline/jira-state")
async def pipeline_jira_state(db: AsyncSession = Depends(get_db)):
    import time

    import httpx

    from app.routers.desk import YOU
    from app.services.jira import _HEADERS, _auth

    rows = (await db.execute(
        select(Upgrade.jira_ref).where(
            Upgrade.stage.notin_(("Verified Done", "Cancelled")),
            Upgrade.jira_ref.is_not(None),
            Upgrade.request_type == _SYS_ADMIN_REQUEST_TYPE,
        )
    )).scalars().all()
    refs = sorted(set(rows))
    if not settings.jira_enabled or not refs:
        return {"you": YOU, "available": settings.jira_enabled, "tickets": {}}

    cache = _jira_state_cache
    if cache["refs"] == refs and time.time() - cache["at"] < _JIRA_STATE_TTL:
        return {"you": YOU, "available": True, "tickets": cache["data"]}

    tickets: dict[str, dict] = {}
    try:
        async with httpx.AsyncClient(auth=_auth(), timeout=30, follow_redirects=True) as client:
            for i in range(0, len(refs), 100):
                chunk = refs[i:i + 100]
                resp = await client.get(
                    f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql", headers=_HEADERS,
                    params={"jql": f"key in ({','.join(chunk)})", "fields": "status,assignee,resolutiondate", "maxResults": 100},
                )
                resp.raise_for_status()
                for issue in resp.json().get("issues", []):
                    f = issue["fields"]
                    tickets[issue["key"]] = {
                        "status": f["status"]["name"],
                        "done": f["status"]["statusCategory"]["key"] == "done",
                        "assignee": (f.get("assignee") or {}).get("displayName"),
                        "resolved_at": f.get("resolutiondate"),
                    }
    except httpx.HTTPError:
        # Board falls back to showing everything, and says why.
        return {"you": YOU, "available": False, "tickets": {}}

    cache.update(refs=refs, at=time.time(), data=tickets)
    return {"you": YOU, "available": True, "tickets": tickets}
