from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.customer import Customer
from app.models.customer_tenant_info import CustomerTenantInfo
from app.models.incident import Incident
from app.models.incident_remediation import IncidentRemediation
from app.models.upgrade import Upgrade
from app.models.vms_bug import VmsBug
from app.routers.releases import _version_tuple

router = APIRouter(prefix="/incidents", tags=["incidents"])

SOURCES = ("code", "infra", "ai-tooling", "product")
SEVERITIES = ("Critical", "High", "Medium", "Low")
PHASES = ("Detected", "Fix Identified", "Fix Released", "Remediating Customers", "Closed")
MITIGATION_TYPES = ("accepted_risk", "workaround_applied")


def _enrich(i: Incident) -> dict:
    return {
        "id": i.id,
        "title": i.title,
        "source": i.source,
        "severity": i.severity,
        "phase": i.phase,
        "linked_vms_ref": i.linked_vms_ref,
        "affected_below_version": i.affected_below_version,
        "detail": i.detail,
        "impact": i.impact,
        "root_cause": i.root_cause,
        "resolution": i.resolution,
        "lessons_learned": i.lessons_learned,
        "detection_gap": i.detection_gap,
        "status": i.status,
        "detected_at": i.detected_at,
        "resolved_at": i.resolved_at,
        "created_at": i.created_at,
    }


def _derive_remediation_status(r: IncidentRemediation) -> str:
    if r.upgrade and r.upgrade.stage == "Verified Done":
        return "Done"
    if r.manually_resolved:
        return "Resolved (manual)"
    if r.mitigation_type == "accepted_risk":
        return f"Accepted risk (review {r.review_by_date.isoformat()})" if r.review_by_date else "Accepted risk"
    if r.mitigation_type == "workaround_applied":
        return "Workaround applied"
    return "In progress"


def _enrich_remediation(r: IncidentRemediation, notified: bool = False) -> dict:
    return {
        "id": r.id,
        "customer_id": r.customer_id,
        "customer_name": r.customer.name if r.customer else None,
        "customer_tier": r.customer.tier if r.customer else None,
        "upgrade_id": r.upgrade_id,
        "upgrade_stage": r.upgrade.stage if r.upgrade else None,
        "upgrade_to_version": r.upgrade.to_version if r.upgrade else None,
        "manually_resolved": r.manually_resolved,
        "notes": r.notes,
        "mitigation_type": r.mitigation_type,
        "mitigation_owner": r.mitigation_owner,
        "mitigation_note": r.mitigation_note,
        "review_by_date": r.review_by_date,
        "derived_status": _derive_remediation_status(r),
        "notified": notified,
    }


@router.get("")
async def list_incidents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Incident).order_by(Incident.detected_at.desc()))
    return [_enrich(i) for i in result.scalars().all()]


@router.post("", status_code=201)
async def create_incident(data: dict, db: AsyncSession = Depends(get_db)):
    title = data.get("title")
    source = data.get("source")
    detail = data.get("detail")
    severity = data.get("severity")
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    if source not in SOURCES:
        raise HTTPException(status_code=400, detail=f"source must be one of {SOURCES}")
    if not detail:
        raise HTTPException(status_code=400, detail="detail is required")
    if severity not in SEVERITIES:
        raise HTTPException(status_code=400, detail=f"severity must be one of {SEVERITIES}")

    detected_at_raw = data.get("detected_at")
    detected_at = datetime.fromisoformat(detected_at_raw) if detected_at_raw else datetime.utcnow()

    incident = Incident(
        title=title,
        source=source,
        severity=severity,
        phase="Detected",
        linked_vms_ref=data.get("linked_vms_ref"),
        affected_below_version=data.get("affected_below_version"),
        detail=detail,
        impact=data.get("impact"),
        status="Open",
        detected_at=detected_at,
    )
    db.add(incident)
    await db.flush()
    db.add(AuditLog(
        actor="you", action="incident.logged", target_type="incident",
        target_id=str(incident.id), detail=f"[{source}] {title}",
    ))
    await db.commit()
    await db.refresh(incident)
    return _enrich(incident)


@router.get("/{incident_id}")
async def get_incident(incident_id: int, db: AsyncSession = Depends(get_db)):
    incident = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    remediations = (
        await db.execute(
            select(IncidentRemediation)
            .where(IncidentRemediation.incident_id == incident_id)
            .options(joinedload(IncidentRemediation.customer), joinedload(IncidentRemediation.upgrade))
        )
    ).scalars().all()

    notified_customer_ids = await _notified_customer_ids(incident_id, db)
    manually_notified_remediation_ids = await _manually_notified_remediation_ids(remediations, db)

    out = _enrich(incident)
    out["remediations"] = [
        _enrich_remediation(
            r,
            notified=r.customer_id in notified_customer_ids or r.id in manually_notified_remediation_ids,
        )
        for r in remediations
    ]
    return out


async def _notified_customer_ids(incident_id: int, db: AsyncSession) -> set[int]:
    """A customer counts as notified once they appear in a Sent Campaign
    linked to this incident — real notification, not a bare toggle (see
    Campaign.incident_id)."""
    campaigns = (
        await db.execute(
            select(Campaign).where(Campaign.incident_id == incident_id, Campaign.status == "Sent")
        )
    ).scalars().all()
    ids: set[int] = set()
    for c in campaigns:
        ids.update(int(v) for v in c.customer_ids.split(",") if v)
    return ids


async def _manually_notified_remediation_ids(remediations: list[IncidentRemediation], db: AsyncSession) -> set[int]:
    """Fallback for a customer notified some other way (a phone call, a
    one-off email) where a formal Campaign doesn't fit — see
    POST /{incident_id}/remediations/{remediation_id}/notify."""
    if not remediations:
        return set()
    ids = [str(r.id) for r in remediations]
    result = await db.execute(
        select(AuditLog.target_id).where(
            AuditLog.target_type == "incident_remediation",
            AuditLog.target_id.in_(ids),
            AuditLog.action == "incident.customer_notified",
        )
    )
    return {int(row[0]) for row in result.all()}


async def _outstanding_remediations(incident_id: int, db: AsyncSession) -> list[IncidentRemediation]:
    remediations = (
        await db.execute(
            select(IncidentRemediation)
            .where(IncidentRemediation.incident_id == incident_id)
            .options(joinedload(IncidentRemediation.customer), joinedload(IncidentRemediation.upgrade))
        )
    ).scalars().all()
    return [
        r for r in remediations
        if not r.manually_resolved
        and not (r.upgrade and r.upgrade.stage == "Verified Done")
        and r.mitigation_type not in MITIGATION_TYPES
    ]


@router.post("/{incident_id}/remediations", status_code=201)
async def add_remediation(incident_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    incident = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    customer_id = data.get("customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required")

    existing = (
        await db.execute(
            select(IncidentRemediation).where(
                IncidentRemediation.incident_id == incident_id,
                IncidentRemediation.customer_id == customer_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="This customer is already listed on this incident")

    remediation = IncidentRemediation(
        incident_id=incident_id, customer_id=customer_id, upgrade_id=data.get("upgrade_id"),
    )
    db.add(remediation)
    await db.commit()
    await db.refresh(remediation, attribute_names=["customer", "upgrade"])
    return _enrich_remediation(remediation)


@router.patch("/{incident_id}/remediations/{remediation_id}")
async def update_remediation(incident_id: int, remediation_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    remediation = (
        await db.execute(
            select(IncidentRemediation).where(
                IncidentRemediation.id == remediation_id, IncidentRemediation.incident_id == incident_id,
            )
        )
    ).scalar_one_or_none()
    if not remediation:
        raise HTTPException(status_code=404, detail="Remediation not found")

    if data.get("manually_resolved") and not (data.get("notes") or remediation.notes):
        raise HTTPException(status_code=400, detail="notes are required when resolving manually")

    if "mitigation_type" in data and data["mitigation_type"]:
        if data["mitigation_type"] not in MITIGATION_TYPES:
            raise HTTPException(status_code=400, detail=f"mitigation_type must be one of {MITIGATION_TYPES}")
        owner = data.get("mitigation_owner") or remediation.mitigation_owner
        note = data.get("mitigation_note") or remediation.mitigation_note
        review_by = data.get("review_by_date") or remediation.review_by_date
        if not (owner and note and review_by):
            raise HTTPException(
                status_code=400,
                detail="mitigation_owner, mitigation_note, and review_by_date are all required together",
            )

    for key, value in data.items():
        if key == "review_by_date" and isinstance(value, str) and value:
            value = date.fromisoformat(value)
        if hasattr(remediation, key) and key not in ("id", "created_at", "incident_id", "customer_id"):
            setattr(remediation, key, value)

    await db.commit()
    await db.refresh(remediation, attribute_names=["customer", "upgrade"])
    return _enrich_remediation(remediation)


@router.post("/{incident_id}/remediations/{remediation_id}/notify", status_code=201)
async def notify_remediation(incident_id: int, remediation_id: int, db: AsyncSession = Depends(get_db)):
    """Manual fallback for a customer notified some other way (a phone
    call, a one-off email) where a formal Campaign doesn't fit — see
    _manually_notified_remediation_ids(). The preferred path is linking a
    real Campaign via Campaign.incident_id instead."""
    remediation = (
        await db.execute(
            select(IncidentRemediation)
            .where(IncidentRemediation.id == remediation_id, IncidentRemediation.incident_id == incident_id)
            .options(joinedload(IncidentRemediation.customer))
        )
    ).scalar_one_or_none()
    if not remediation:
        raise HTTPException(status_code=404, detail="Remediation not found")

    name = remediation.customer.name if remediation.customer else f"customer {remediation.customer_id}"
    db.add(AuditLog(
        actor="you", action="incident.customer_notified", target_type="incident_remediation",
        target_id=str(remediation.id), detail=f"{name} notified manually",
    ))
    await db.commit()
    return {"notified": True}


@router.post("/{incident_id}/decisions", status_code=201)
async def log_decision(incident_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    incident = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    text = (data.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    db.add(AuditLog(
        actor="you", action="incident.decision_logged", target_type="incident",
        target_id=str(incident_id), detail=text,
    ))
    await db.commit()
    return {"logged": True}


@router.get("/{incident_id}/timeline")
async def get_incident_timeline(incident_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.target_type == "incident", AuditLog.target_id == str(incident_id))
        .order_by(AuditLog.created_at.desc())
    )
    return [
        {"action": row.action, "detail": row.detail, "actor": row.actor, "created_at": row.created_at}
        for row in result.scalars().all()
    ]


@router.get("/{incident_id}/suggest-customers")
async def suggest_customers(incident_id: int, min_version: str | None = None, db: AsyncSession = Depends(get_db)):
    """Honest assist, not a promise — only surfaces candidates where real
    CustomerTenantInfo data exists (44/576 customers, confirmed elsewhere
    this session). Never fabricates a suggestion from Customer.prod_version,
    which is fake seed data for all but 7 customers.

    Three ways to get a fix threshold, in order of preference:
    1. `min_version` passed explicitly for this one call.
    2. `incident.affected_below_version` — the persisted threshold (see
       Incident model) — set once, reused by every future suggestion AND
       by the automatic match-on-sync in customers.py::sync_tenant_info().
    3. Fall back to the linked VmsBug's real fix_version.
    Doesn't require a correctly-linked VmsBug at all — confirmed live this
    matters: an incident's linked_vms_ref can be a placeholder/typo'd value
    with no matching VmsBug row, which silently produced zero suggestions
    before this.
    """
    incident = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    fix_tuple = _version_tuple(min_version) if min_version else None
    if fix_tuple is None and incident.affected_below_version:
        fix_tuple = _version_tuple(incident.affected_below_version)
    if fix_tuple is None and incident.linked_vms_ref:
        bug = (await db.execute(select(VmsBug).where(VmsBug.jira_ref == incident.linked_vms_ref))).scalar_one_or_none()
        if bug and bug.fix_version:
            fix_tuple = _version_tuple(bug.fix_version)
    if fix_tuple is None:
        return []

    already_listed = {
        r.customer_id for r in (
            await db.execute(select(IncidentRemediation).where(IncidentRemediation.incident_id == incident_id))
        ).scalars().all()
    }

    prod_rows = (
        await db.execute(select(CustomerTenantInfo).where(CustomerTenantInfo.environment == "PROD"))
    ).scalars().all()
    customer_ids = {r.customer_id for r in prod_rows if r.release}
    customers_by_id = {
        c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars().all()
    } if customer_ids else {}

    candidates = []
    for row in prod_rows:
        if not row.release or row.customer_id in already_listed:
            continue
        row_tuple = _version_tuple(row.release)
        if row_tuple and row_tuple < fix_tuple:
            cust = customers_by_id.get(row.customer_id)
            if cust:
                candidates.append({"id": cust.id, "name": cust.name, "tier": cust.tier, "prod_version": row.release})
    return sorted(candidates, key=lambda c: c["name"])


async def check_incident_matches_on_sync(db: AsyncSession, customer: Customer, version: str) -> list[dict]:
    """Called right after a PROD tenant-info sync learns a customer's real
    version (customers.py::sync_tenant_info()). Checks every open product
    incident's fix threshold — affected_below_version, falling back to the
    linked VmsBug's fix_version, same preference order as suggest_customers()
    — and auto-creates an IncidentRemediation row for this customer when
    their newly-synced version is below it and they aren't already listed.
    Never commits — the caller (already inside its own sync transaction)
    commits once. Returns the matched incidents for a toast/response."""
    version_tuple = _version_tuple(version)
    if version_tuple is None:
        return []

    incidents = (
        await db.execute(select(Incident).where(Incident.source == "product", Incident.status == "Open"))
    ).scalars().all()

    matched = []
    for incident in incidents:
        fix_tuple = _version_tuple(incident.affected_below_version) if incident.affected_below_version else None
        if fix_tuple is None and incident.linked_vms_ref:
            bug = (await db.execute(select(VmsBug).where(VmsBug.jira_ref == incident.linked_vms_ref))).scalar_one_or_none()
            if bug and bug.fix_version:
                fix_tuple = _version_tuple(bug.fix_version)
        if fix_tuple is None or not (version_tuple < fix_tuple):
            continue

        existing = (
            await db.execute(
                select(IncidentRemediation).where(
                    IncidentRemediation.incident_id == incident.id,
                    IncidentRemediation.customer_id == customer.id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue

        db.add(IncidentRemediation(incident_id=incident.id, customer_id=customer.id))
        db.add(AuditLog(
            actor="system", action="incident.auto_matched", target_type="incident",
            target_id=str(incident.id), detail=f"{customer.name} (synced {version}) — matched via sync",
        ))
        matched.append({"incident_id": incident.id, "incident_title": incident.title})

    return matched


@router.patch("/{incident_id}")
async def update_incident(incident_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    incident = (await db.execute(select(Incident).where(Incident.id == incident_id))).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if "severity" in data and data["severity"] not in SEVERITIES:
        raise HTTPException(status_code=400, detail=f"severity must be one of {SEVERITIES}")
    if "phase" in data and data["phase"] not in PHASES:
        raise HTTPException(status_code=400, detail=f"phase must be one of {PHASES}")

    new_status = data.get("status")
    if new_status == "Resolved" and incident.source == "product":
        outstanding = await _outstanding_remediations(incident_id, db)
        if outstanding:
            names = ", ".join(r.customer.name if r.customer else f"customer {r.customer_id}" for r in outstanding)
            raise HTTPException(
                status_code=400,
                detail=f"{len(outstanding)} affected customer(s) haven't completed their upgrade yet: {names}",
            )

    for key, value in data.items():
        if hasattr(incident, key) and key not in ("id", "created_at"):
            setattr(incident, key, value)

    if new_status == "Resolved" and incident.resolved_at is None:
        incident.resolved_at = datetime.utcnow()
        db.add(AuditLog(
            actor="you", action="incident.resolved", target_type="incident",
            target_id=str(incident.id), detail=incident.title,
        ))

    await db.commit()
    await db.refresh(incident)
    return _enrich(incident)
