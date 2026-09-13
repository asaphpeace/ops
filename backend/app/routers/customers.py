from datetime import date as dt_date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.customer import Customer
from app.models.customer_tenant_info import CustomerTenantInfo
from app.models.migration_project import MigrationProject
from app.models.release import Release
from app.models.note import CustomerNote
from app.models.customer_contact import CustomerContact
from app.schemas.customer import CustomerOut, CustomerDetail, CustomerCreate, CustomerUpdate, NoteOut, ContactOut
from app.schemas.customer_tenant_info import TenantInfoCreate, TenantInfoOut
from app.services.jira import customer_case_stats, real_open_counts_by_customer, resolve_customer_contacts
from app.routers.incidents import check_incident_matches_on_sync
from app.routers.releases import _version_tuple

router = APIRouter(prefix="/customers", tags=["customers"])


class NotifyContactsRequest(BaseModel):
    customer_ids: list[int]


@router.post("/notify/resolve-contacts")
async def notify_resolve_contacts(body: NotifyContactsRequest, db: AsyncSession = Depends(get_db)):
    """Real contacts for a customer broadcast (e.g. a maintenance-window
    notice) — combines two sources, not just one. The live Jira Service
    Management Organization lookup (resolve_customer_contacts()) only ever
    matches a real Organization for a fraction of customers (confirmed live:
    17 of 81 real VMS customers, ~21% — the rest have no JSM Organization
    record at all, so the live-only path returned nothing for the other
    79%). The already-real, already-validated CustomerContact table (the
    same one behind each customer's Contacts tab, seeded from Jira/Confluence
    search) covers far more customers and must be merged in here too, not
    left as a separate, disconnected data source. No sending happens here or
    anywhere in this app; this only assembles who to contact."""
    if not body.customer_ids:
        return []
    results = await resolve_customer_contacts(body.customer_ids, db)

    stored = await db.execute(
        select(CustomerContact).where(CustomerContact.customer_id.in_(body.customer_ids))
    )
    stored_by_customer: dict[int, list[CustomerContact]] = {}
    for row in stored.scalars().all():
        stored_by_customer.setdefault(row.customer_id, []).append(row)

    for r in results:
        rows = stored_by_customer.get(r["customer_id"], [])
        primary_emails = {row.email.lower() for row in rows if row.is_primary}

        existing = {c["email"].lower() for c in r["contacts"] if c["email"]}
        for c in r["contacts"]:
            if c["email"]:
                c["primary"] = c["email"].lower() in primary_emails
        for row in rows:
            if row.email.lower() not in existing:
                r["contacts"].append({"name": None, "email": row.email, "primary": row.email.lower() in primary_emails})
                existing.add(row.email.lower())
        r["email_count"] = len([c for c in r["contacts"] if c["email"]])

        # The one email that actually goes in an outbound send list — the
        # designated main/technical contact (see designate_primary_contacts.py)
        # when one exists, or the sole contact when there's only ever been
        # one to choose from (covers customers resolved only via the live
        # Jira org lookup, which the designation script never touches).
        # Ambiguous (2+ real contacts, none designated) is left None rather
        # than guessed — the frontend falls back to every email for that one
        # customer instead of silently dropping them.
        real_emails = [c["email"] for c in r["contacts"] if c["email"]]
        if primary_emails:
            r["primary_contact_email"] = next(e for e in real_emails if e.lower() in primary_emails)
        elif len(real_emails) == 1:
            r["primary_contact_email"] = real_emails[0]
        else:
            r["primary_contact_email"] = None
    return results


@router.get("", response_model=list[CustomerOut])
async def list_customers(
    tier: str | None = None,
    csm: str | None = None,
    infra: str | None = None,
    health_max: int | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Customer)
    if status == "all":
        pass  # no filter — every customer regardless of status
    elif status:
        q = q.where(Customer.status == status)
    else:
        # Default view is active customers only — cancelled ones (infra
        # decommissioned) shouldn't clutter the working list. Pass
        # status=all to see everyone, or status=Cancelled for just those.
        q = q.where(Customer.status != "Cancelled")
    if tier:
        q = q.where(Customer.tier == tier)
    if csm:
        q = q.where(Customer.csm == csm)
    if infra:
        q = q.where(Customer.infra == infra)
    if health_max is not None:
        q = q.where(Customer.health_score <= health_max)
    q = q.order_by(Customer.name)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/stats")
async def customer_stats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Customer).where(Customer.status != "Cancelled"))
    customers = result.scalars().all()

    arr_old_infra = sum(c.arr_gbp for c in customers if c.infra == "Old")
    arr_red_health = sum(c.arr_gbp for c in customers if c.health_score <= 45)
    # Deliberately a combined metric, not just "renewing soon": a healthy
    # customer renewing imminently isn't a real risk in the CS sense, so this
    # is health<=70 AND renewing<=60d together — the frontend card is
    # labeled "At Renewal Risk · <=60d away + health <=70" to say so
    # honestly, rather than the old bare "renewing within 60d" subtitle that
    # silently didn't mention the health gate.
    arr_renewal_risk = sum(
        c.arr_gbp for c in customers
        if c.health_score <= 70 and c.renewal_date and
        0 <= (c.renewal_date - dt_date.today()).days <= 60
    )

    defect_ids_result = await db.execute(
        select(Case.customer_id).where(
            Case.case_type == "Defect",
            Case.status != "Closed",
        ).distinct()
    )
    defect_customer_ids = set(defect_ids_result.scalars().all())
    arr_open_defects = sum(c.arr_gbp for c in customers if c.id in defect_customer_ids)

    # Infra-focused numbers for Customer Intelligence's own strip (Trends
    # keeps using the ARR fields above for its portfolio/account-health
    # framing — these are additive, not a replacement). All scoped to real
    # VMS customers, not the full active-customer list: confirmed live that
    # `infra` is a leftover/default field on non-VMS accounts too — 533 of
    # 558 active customers show infra="Old", but only 53 of those are
    # actually VMS customers (the other 480 are Email/CompassAir-only
    # accounts with no real AWS VMS infrastructure to migrate at all).
    # Reporting the unscoped 533 on an "infrastructure migration" card would
    # be honestly meaningless — VMS customers are the only population this
    # concept applies to.
    vms_customer_ids = {c.id for c in customers if c.product and "VMS" in c.product.upper()}
    vms_old_infra_count = sum(1 for c in customers if c.id in vms_customer_ids and c.infra == "Old")

    migrations = (await db.execute(select(MigrationProject))).scalars().all()
    vms_migrations = [m for m in migrations if m.customer_id in vms_customer_ids]
    migration_active_count = sum(1 for m in vms_migrations if m.stage not in ("Not Started", "Complete"))
    stalled_migration_count = sum(1 for m in vms_migrations if m.stalled)

    # Version data: Customer.prod_version is fake seed data (confirmed
    # earlier this session — only 7 hand-seeded rows, no real sync path).
    # CustomerTenantInfo is the real source, but sparse — scoped to VMS
    # customers only (the only population it realistically applies to) so
    # the coverage fraction means something, rather than diluting it against
    # ~500 Email-only customers who were never expected to have tenant data.
    latest_release = (await db.execute(select(Release).where(Release.is_latest == True))).scalar_one_or_none()  # noqa: E712
    confirmed_outdated_count = 0
    tenant_known_count = 0
    if latest_release and vms_customer_ids:
        latest_tuple = _version_tuple(latest_release.version)
        prod_rows = (await db.execute(
            select(CustomerTenantInfo).where(
                CustomerTenantInfo.environment == "PROD",
                CustomerTenantInfo.customer_id.in_(vms_customer_ids),
            )
        )).scalars().all()
        tenant_known_count = sum(1 for r in prod_rows if r.release)
        if latest_tuple:
            for row in prod_rows:
                row_tuple = _version_tuple(row.release)
                if row_tuple and row_tuple < latest_tuple:
                    confirmed_outdated_count += 1

    return {
        "total": len(customers),
        "arr_old_infra": arr_old_infra,
        "arr_red_health": arr_red_health,
        "arr_renewal_risk": arr_renewal_risk,
        "arr_open_defects": arr_open_defects,
        "old_infra_count": sum(1 for c in customers if c.infra == "Old"),
        "red_health_count": sum(1 for c in customers if c.health_score <= 45),
        "vms_old_infra_count": vms_old_infra_count,
        "migration_active_count": migration_active_count,
        "stalled_migration_count": stalled_migration_count,
        "confirmed_outdated_count": confirmed_outdated_count,
        "tenant_known_count": tenant_known_count,
        "vms_customer_count": len(vms_customer_ids),
        "latest_version": latest_release.version if latest_release else None,
    }


@router.get("/open-case-counts")
async def open_case_counts(db: AsyncSession = Depends(get_db)):
    """Real, live-Jira open-case count per customer, for the Customers list's
    "Open Cases" column — that column previously counted *every* local
    `cases` row (open AND closed, no status filter at all) for a customer,
    confirmed live to badly undercount real volume the same way every other
    local-table-only view did this session (a real customer showed 23 local
    rows vs. 95 real open tickets). Reuses real_open_counts_by_customer(),
    same free-reuse of team_open_stats()'s cache as Volume by Account — no
    new Jira fetch. Falls back to the old local-table count only when Jira
    is disabled or the live fetch fails.
    """
    if settings.jira_enabled:
        try:
            real_counts = await real_open_counts_by_customer(db)
            return {"counts": {cid: v["open_count"] for cid, v in real_counts.items()}, "source": "jira_live"}
        except Exception:
            pass  # degrade to the local-table fallback below

    result = await db.execute(select(Case.customer_id, Case.status))
    counts: dict[int, int] = {}
    for customer_id, status in result.all():
        if status != "Closed":
            counts[customer_id] = counts.get(customer_id, 0) + 1
    return {"counts": counts, "source": "local_fallback"}


@router.get("/triage")
async def customer_triage(db: AsyncSession = Depends(get_db)):
    """VMS customers grouped with active cases and computed risk signals for the triage queue."""
    result = await db.execute(
        select(Customer)
        .where(Customer.product.ilike("%VMS%"))
        .options(
            selectinload(Customer.cases),
            selectinload(Customer.training_gaps),
            selectinload(Customer.upgrades),
        )
    )
    customers = result.scalars().all()

    today = dt_date.today()

    from app.services.temperature import compute as compute_temp
    from app.models.release import Release

    latest_result = await db.execute(
        select(Release).where(Release.is_latest == True)  # noqa: E712
    )
    latest_release = latest_result.scalar_one_or_none()
    latest_version = latest_release.version if latest_release else None

    output = []
    for c in customers:
        active_cases = [case for case in c.cases if case.status != "Closed"]
        high_open = sum(1 for case in active_cases if case.priority == "High")
        gap_count = sum(g.count for g in c.training_gaps)

        last_upgrade = max(
            (u.date_done for u in c.upgrades if u.date_done and u.stage == "Verified Done"),
            default=None,
        )
        days_since_upgrade = (today - last_upgrade.date()).days if last_upgrade else None

        temperature = compute_temp(
            prod_version=c.prod_version,
            latest_version=latest_version,
            high_priority_open=high_open,
            training_gap_count=gap_count,
            days_since_upgrade=days_since_upgrade,
            infra=c.infra,
            sentiment=c.sentiment,
        )

        sso_pts = 35 if (c.sso and c.sso != "None") else 0
        hygiene_pts = 20
        infra_pts = 30 if c.infra == "New" else (15 if c.infra == "Mixed" else 0)
        if c.wildfly8:
            infra_pts = max(0, infra_pts - 5)
        security_score = sso_pts + hygiene_pts + infra_pts

        renewal_days = (c.renewal_date - today).days if c.renewal_date else None

        sla_breaching = [
            case for case in active_cases
            if case.sla_days and case.days_open > case.sla_days
        ]

        if len(sla_breaching) >= 2 or (sla_breaching and c.health_score <= 30):
            risk = "high"
        elif sla_breaching or c.health_score <= 50 or any(case.blocked for case in active_cases):
            risk = "action"
        else:
            risk = "monitor"

        output.append({
            "id": c.id,
            "name": c.name,
            "tier": c.tier,
            "arr_gbp": c.arr_gbp,
            "infra": c.infra,
            "wildfly8": c.wildfly8,
            "sso": c.sso,
            "prod_version": c.prod_version,
            "temperature": temperature,
            "security_score": security_score,
            "renewal_days": renewal_days,
            "risk": risk,
            "training_gap_count": gap_count,
            "sla_breaching_count": len(sla_breaching),
            "hypercare_until": c.hypercare_until,
            "hypercare_reason": c.hypercare_reason,
            "active_case_count": len(active_cases),
            "active_cases": [
                {
                    "id": case.id,
                    "jira_ref": case.jira_ref,
                    "sla_breaching": bool(case.sla_days and case.days_open > case.sla_days),
                }
                for case in active_cases[:5]
            ],
        })

    output.sort(key=lambda r: ({"high": 0, "action": 1, "monitor": 2}[r["risk"]], r["renewal_days"] or 9999))
    return output


@router.get("/{customer_id}", response_model=CustomerDetail)
async def get_customer(customer_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Customer)
        .where(Customer.id == customer_id)
        .options(
            selectinload(Customer.cases),
            selectinload(Customer.upgrades),
            selectinload(Customer.migration),
            selectinload(Customer.training_gaps),
            selectinload(Customer.training_sessions),
            selectinload(Customer.notes),
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


# Real Dataloy plan allowances (dataloy-systems.com/plans, confirmed 2026-08-25):
# Starter 4/yr, Growth 4/yr, Professional 8/yr, Enterprise 12/yr. Sedna's own
# tiers map onto these 1:1 (confirmed with the user, skipping Growth since
# Sedna only has three tiers) — Scale=Starter, Strategic=Professional,
# Premier=Enterprise. upgrades_limit is a function of tier, not a free-typed
# number — every one of the 537 existing customers had drifted to a flat 10
# regardless of tier before this was enforced here.
TIER_UPGRADE_LIMITS = {"Scale": 4, "Strategic": 8, "Premier": 12}

# Premier is the only tier whose package includes after-hours upgrade slots
# by default (4/yr — half the PROD allowance, in line with the "nominally
# 2hr" after-hours billing unit). Scale/Strategic default to ineligible but
# can be flipped per-customer via PATCH — this is a starting default, not a
# hard rule, confirmed with the user.
TIER_AFTER_HOURS_DEFAULTS = {"Premier": (True, 4), "Strategic": (False, 0), "Scale": (False, 0)}


@router.post("", response_model=CustomerOut, status_code=201)
async def create_customer(data: CustomerCreate, db: AsyncSession = Depends(get_db)):
    payload = data.model_dump()
    if payload.get("tier") in TIER_UPGRADE_LIMITS:
        payload["upgrades_limit"] = TIER_UPGRADE_LIMITS[payload["tier"]]
    if payload.get("tier") in TIER_AFTER_HOURS_DEFAULTS:
        eligible, limit = TIER_AFTER_HOURS_DEFAULTS[payload["tier"]]
        payload["after_hours_eligible"] = eligible
        payload["after_hours_limit"] = limit
    customer = Customer(**payload)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(customer_id: int, data: CustomerUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    payload = data.model_dump(exclude_none=True)
    if "tier" in payload and payload["tier"] in TIER_UPGRADE_LIMITS:
        payload["upgrades_limit"] = TIER_UPGRADE_LIMITS[payload["tier"]]
    # Guarded by "not in payload" (unlike upgrades_limit above) so an
    # explicit after_hours_eligible/after_hours_limit passed in the same
    # request isn't silently stomped by the tier default whenever tier is
    # resent unchanged.
    if "tier" in payload and payload["tier"] in TIER_AFTER_HOURS_DEFAULTS:
        eligible, limit = TIER_AFTER_HOURS_DEFAULTS[payload["tier"]]
        if "after_hours_eligible" not in payload:
            payload["after_hours_eligible"] = eligible
        if "after_hours_limit" not in payload:
            payload["after_hours_limit"] = limit
    hypercare_newly_set = "hypercare_until" in payload and customer.hypercare_until is None
    for key, value in payload.items():
        setattr(customer, key, value)
    if hypercare_newly_set:
        db.add(AuditLog(
            actor="you", action="customer.hypercare_set", target_type="customer", target_id=str(customer.id),
            detail=customer.hypercare_reason or None,
        ))
    await db.commit()
    await db.refresh(customer)
    return customer


@router.post("/{customer_id}/clear-hypercare", response_model=CustomerOut)
async def clear_hypercare(customer_id: int, db: AsyncSession = Depends(get_db)):
    """Dedicated action since a normal PATCH (exclude_none=True) can never
    null out a field — same reasoning as the tenant-info sync action below."""
    customer = (await db.execute(select(Customer).where(Customer.id == customer_id))).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.hypercare_until = None
    customer.hypercare_reason = None
    await db.commit()
    await db.refresh(customer)
    return customer


@router.get("/{customer_id}/case-summary")
async def customer_case_summary(customer_id: int, db: AsyncSession = Depends(get_db)):
    """Structured, deterministic rollup — no AI. Counts, open list, oldest age.

    Real, live-Jira-backed (customer_case_stats()) rather than the local
    `cases` table — confirmed live that table only ever holds tickets a
    human has manually mapped via Jira Mapping, undercounting real open
    volume badly (a real customer showed 13 locally vs. 95 real open
    tickets — see customer_case_stats()'s docstring for the full root
    cause). Falls back to the local table only when Jira is disabled or
    the live fetch fails, so this degrades instead of erroring outright.
    """
    customer = (await db.execute(select(Customer).where(Customer.id == customer_id))).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if settings.jira_enabled:
        try:
            stats = await customer_case_stats(customer.name, known_option_value=customer.jira_customer_field_value)
            if stats["matched"]:
                # Persist the discovered option value the first time (or if
                # it ever changes) — see customer_case_stats()'s docstring
                # for why this matters: without it, the discovery scan can
                # intermittently "lose" an otherwise-active customer once
                # other project activity pushes them out of its recency
                # window, even though nothing about the customer changed.
                if customer.jira_customer_field_value != stats["jira_customer_value"]:
                    customer.jira_customer_field_value = stats["jira_customer_value"]
                    await db.commit()
                return {
                    "customer_id": customer_id,
                    "customer_name": customer.name,
                    "source": "jira_live",
                    "logged_months": stats["logged_months"],
                    "open_count": stats["open_count"],
                    "by_case_type": stats["by_case_type"],
                    "by_priority": stats["by_priority"],
                    "oldest_days": stats["oldest_days"],
                    "open_tickets": stats["open_tickets"],
                    "monthly_counts": stats["monthly_counts"],
                    "top_topics": stats["top_topics"],
                    "recurring_topics": stats["recurring_topics"],
                    "volume_spike": stats["volume_spike"],
                }
        except Exception:
            pass  # degrade to the local-table fallback below

    cases = (await db.execute(select(Case).where(Case.customer_id == customer_id))).scalars().all()
    open_cases = [c for c in cases if c.status != "Closed"]

    by_type: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for c in open_cases:
        by_type[c.case_type] = by_type.get(c.case_type, 0) + 1
        by_priority[c.priority] = by_priority.get(c.priority, 0) + 1

    return {
        "customer_id": customer_id,
        "customer_name": customer.name,
        "source": "local_fallback",
        "logged_months": None,
        "open_count": len(open_cases),
        "by_case_type": by_type,
        "by_priority": by_priority,
        "oldest_days": max((c.days_open for c in open_cases), default=0),
        "open_tickets": [
            {"jira_ref": c.jira_ref, "title": c.title, "priority": c.priority, "days_open": c.days_open}
            for c in sorted(open_cases, key=lambda c: c.days_open, reverse=True)
        ],
        # Not computable from the local, badly-undercounted cases table —
        # honestly empty rather than fabricated, same bar as "matched: False"
        # in customer_case_stats() itself.
        "monthly_counts": [], "top_topics": [], "recurring_topics": [], "volume_spike": None,
    }


@router.get("/{customer_id}/tenant-info", response_model=list[TenantInfoOut])
async def list_tenant_info(customer_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CustomerTenantInfo).where(CustomerTenantInfo.customer_id == customer_id).order_by(CustomerTenantInfo.environment)
    )
    return result.scalars().all()


@router.post("/{customer_id}/tenant-info", response_model=TenantInfoOut, status_code=201)
async def set_tenant_subdomain(customer_id: int, data: TenantInfoCreate, db: AsyncSession = Depends(get_db)):
    """Manual step — tenant subdomains don't follow one consistent naming
    rule (confirmed: some are a bare code for prod with no suffix, others
    use an explicit -prod/-test suffix), so there's nothing to derive this
    from. Upserts by (customer_id, environment)."""
    customer = (await db.execute(select(Customer).where(Customer.id == customer_id))).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    result = await db.execute(
        select(CustomerTenantInfo).where(
            CustomerTenantInfo.customer_id == customer_id,
            CustomerTenantInfo.environment == data.environment,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.subdomain = data.subdomain
    else:
        row = CustomerTenantInfo(customer_id=customer_id, environment=data.environment, subdomain=data.subdomain)
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.post("/{customer_id}/tenant-info/{environment}/sync", response_model=TenantInfoOut)
async def sync_tenant_info(customer_id: int, environment: str, db: AsyncSession = Depends(get_db)):
    """On-demand only — this hits customer-owned infrastructure directly,
    never scheduled. A click of the button returns the fresh result.

    A successful PROD/TEST sync also writes the real release straight onto
    Customer.prod_version/test_version — every other screen that shows a
    customer's running version (Customer Intelligence, Trends, Releases,
    the WildFly inference on this same panel's Overview tab) already reads
    those two fields directly, so this is what actually makes a sync here
    "reflect everywhere" rather than only updating the Technical tab's own
    CustomerTenantInfo row."""
    from app.services.tenant_info import fetch_tenant_info

    result = await db.execute(
        select(CustomerTenantInfo).where(
            CustomerTenantInfo.customer_id == customer_id,
            CustomerTenantInfo.environment == environment,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="No subdomain configured for this environment yet")

    probe = await fetch_tenant_info(row.subdomain)
    row.last_synced_at = datetime.utcnow()
    matched_incidents: list[dict] = []
    if probe.error:
        row.last_sync_error = probe.error
    else:
        data = probe.data or {}
        row.release = data.get("release")
        row.reported_environment = data.get("environment")
        row.is_azure_installation = data.get("isAzureInstallation")
        row.is_auth0_installation = data.get("isAuth0Installation")
        row.is_jvms_mode = data.get("jvmsMode")
        row.is_pure_web = data.get("isPureWeb")
        row.last_sync_error = None

        if row.release and environment in ("PROD", "TEST"):
            customer = (await db.execute(select(Customer).where(Customer.id == customer_id))).scalar_one_or_none()
            if customer:
                if environment == "PROD":
                    customer.prod_version = row.release
                    # Mass-mitigation planning: the moment a synced PROD
                    # version is known, check it against every open product
                    # incident's fix threshold and auto-link this customer
                    # as affected — no manual "suggest customers" step needed.
                    matched_incidents = await check_incident_matches_on_sync(db, customer, row.release)
                else:
                    customer.test_version = row.release

    await db.commit()
    await db.refresh(row)
    if environment == "PROD":
        row.matched_incidents = matched_incidents
    return row


@router.get("/{customer_id}/vms-credential")
async def get_vms_credential(customer_id: int, db: AsyncSession = Depends(get_db)):
    """Never returns client_secret — it's a real secret, not a display
    value. client_id is echoed back (an identifier, not a secret) so the UI
    can show what's configured without needing to re-paste it."""
    from app.models.vms_api_credential import VmsApiCredential

    row = (await db.execute(
        select(VmsApiCredential).where(VmsApiCredential.customer_id == customer_id)
    )).scalar_one_or_none()
    if not row:
        return {"has_credential": False, "label": None, "client_id": None, "audience": None}
    return {"has_credential": True, "label": row.label, "client_id": row.client_id, "audience": row.audience}


@router.post("/{customer_id}/vms-credential")
async def set_vms_credential(customer_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    """Write-only upsert of a customer's Dataloy VMS M2M credential —
    client_secret is a real secret and is never returned by any GET, so
    this is a dedicated action rather than a field on the generic customer
    PATCH (same reasoning as clear-hypercare above)."""
    from app.models.vms_api_credential import VmsApiCredential

    customer = (await db.execute(select(Customer).where(Customer.id == customer_id))).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if not data.get("client_id") or not data.get("client_secret"):
        raise HTTPException(status_code=400, detail="client_id and client_secret are required")

    row = (await db.execute(
        select(VmsApiCredential).where(VmsApiCredential.customer_id == customer_id)
    )).scalar_one_or_none()
    if not row:
        row = VmsApiCredential(customer_id=customer_id)
        db.add(row)
    row.label = data.get("label") or customer.name
    row.client_id = data["client_id"]
    row.client_secret = data["client_secret"]
    row.audience = data.get("audience") or "https://dataloy"
    row.cached_token = None
    row.token_expires_at = None
    await db.commit()
    return {"has_credential": True, "label": row.label, "client_id": row.client_id, "audience": row.audience}


@router.get("/{customer_id}/vms-entity")
async def get_vms_entity(customer_id: int, entity: str, key: str, demo: bool = False, db: AsyncSession = Depends(get_db)):
    """Raw explorer, not a polished feature by design — the exact entity
    name for 'tenant configuration' isn't confirmed yet (see the plan file),
    so this lets a real engineer find out with real data instead of the app
    guessing a fixed screen. `demo=true` uses the shared, non-customer-
    specific credential (customer_id IS NULL) instead of this customer's own."""
    import httpx
    from app.config import settings
    from app.models.vms_api_credential import VmsApiCredential
    from app.services.dataloy_vms import VmsNotConfiguredError, get_entity

    if not settings.dataloy_vms_enabled:
        return {"data": None, "message": "Dataloy VMS API not configured (dataloy_vms_token_url/dataloy_vms_api_base_url unset)"}

    lookup_id = None if demo else customer_id
    row = (await db.execute(
        select(VmsApiCredential).where(VmsApiCredential.customer_id == lookup_id)
    )).scalar_one_or_none()
    if not row:
        which = "demo/generic" if demo else "this customer"
        return {"data": None, "message": f"No VMS credential configured for {which} yet"}

    try:
        data = await get_entity(row, db, entity, key)
    except VmsNotConfiguredError as exc:
        return {"data": None, "message": str(exc)}
    except httpx.HTTPStatusError as exc:
        return {"data": None, "message": f"VMS API returned {exc.response.status_code}"}
    except httpx.RequestError as exc:
        return {"data": None, "message": f"VMS API request failed: {exc}"}
    return {"data": data, "message": None}


@router.post("/{customer_id}/summarize")
async def summarize_customer(customer_id: int, db: AsyncSession = Depends(get_db)):
    """On-demand AI summary of what this customer has been reporting. Cached."""
    from app.config import settings
    from app.services.digest import summarize_customer_issues

    customer = (await db.execute(select(Customer).where(Customer.id == customer_id))).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if not settings.ai_enabled:
        return {"summary": None, "message": "ANTHROPIC_API_KEY not set — AI summaries disabled"}

    cases = (
        (await db.execute(select(Case).where(Case.customer_id == customer_id, Case.status != "Closed")))
        .scalars()
        .all()
    )
    summary = await summarize_customer_issues(customer.name, cases, db)
    customer.ai_summary = summary
    customer.ai_summary_at = datetime.utcnow()
    await db.commit()
    return {"summary": summary, "generated_at": customer.ai_summary_at}


@router.get("/{customer_id}/notes", response_model=list[NoteOut])
async def list_notes(customer_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CustomerNote).where(CustomerNote.customer_id == customer_id).order_by(CustomerNote.created_at.desc())
    )
    return result.scalars().all()


@router.post("/{customer_id}/notes", response_model=NoteOut, status_code=201)
async def create_note(customer_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    text = (data.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    customer = (await db.execute(select(Customer).where(Customer.id == customer_id))).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    note = CustomerNote(customer_id=customer_id, text=text, author=data.get("author") or "Asaph")
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


@router.get("/{customer_id}/contacts", response_model=list[ContactOut])
async def list_contacts(customer_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CustomerContact).where(CustomerContact.customer_id == customer_id).order_by(CustomerContact.email)
    )
    return result.scalars().all()


@router.post("/{customer_id}/contacts", response_model=ContactOut, status_code=201)
async def create_contact(customer_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="a real email is required")
    customer = (await db.execute(select(Customer).where(Customer.id == customer_id))).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    existing = await db.execute(
        select(CustomerContact).where(CustomerContact.customer_id == customer_id, CustomerContact.email == email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This email is already on file for this customer")
    contact = CustomerContact(customer_id=customer_id, email=email, source=data.get("source") or "manual")
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.delete("/{customer_id}/contacts/{contact_id}", status_code=204)
async def delete_contact(customer_id: int, contact_id: int, db: AsyncSession = Depends(get_db)):
    contact = (await db.execute(
        select(CustomerContact).where(CustomerContact.id == contact_id, CustomerContact.customer_id == customer_id)
    )).scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(contact)
    await db.commit()


@router.get("/{customer_id}/campaigns")
async def customer_campaigns(customer_id: int, db: AsyncSession = Depends(get_db)):
    """Every campaign this customer was included in — for CustomerDrillPanel's
    Comms tab. Campaigns are created every 2-3 months (a handful of rows,
    ever), so a full-table scan + Python-side comma-split filter is fine —
    same reasoning as bug_linkage.py's cases_by_bug_ref()."""
    from app.models.campaign import Campaign

    result = await db.execute(select(Campaign).order_by(Campaign.created_at.desc()))
    campaigns = result.scalars().all()
    target = str(customer_id)
    return [
        {
            "id": c.id, "name": c.name, "status": c.status,
            "created_at": c.created_at, "sent_at": c.sent_at,
        }
        for c in campaigns
        if target in c.customer_ids.split(",")
    ]
