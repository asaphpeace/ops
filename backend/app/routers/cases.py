from datetime import date as dt_date, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.customer import Customer
from app.schemas.case import CaseCreate, CaseUpdate, CaseOut, CaseDetailOut, CaseTimelineEntry, RelatedCaseSummary
from app.services.lanes import waiting_on

router = APIRouter(prefix="/cases", tags=["cases"])


def _enrich(case: Case) -> dict:
    d = {col.name: getattr(case, col.name) for col in case.__table__.columns}
    if case.customer:
        d["customer_name"] = case.customer.name
        d["customer_tier"] = case.customer.tier
    return d


@router.get("", response_model=list[CaseOut])
async def list_cases(
    status: str | None = None,
    case_type: str | None = None,
    tier: str | None = None,
    customer_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Case).options(joinedload(Case.customer))
    if status:
        q = q.where(Case.status == status)
    if case_type:
        q = q.where(Case.case_type == case_type)
    if customer_id:
        q = q.where(Case.customer_id == customer_id)
    if tier:
        q = q.join(Customer).where(Customer.tier == tier)
    q = q.order_by(Case.days_open.desc())
    result = await db.execute(q)
    cases = result.scalars().all()
    return [CaseOut(**_enrich(c)) for c in cases]


@router.get("/triage")
async def triage_stats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Case).where(Case.status != "Closed").options(joinedload(Case.customer))
    )
    cases = result.scalars().all()

    sla_breaching = [c for c in cases if c.sla_days and c.days_open > c.sla_days]
    awaiting_dev = [c for c in cases if waiting_on(c) == "dev"]
    awaiting_customer = [c for c in cases if c.status == "Awaiting Customer"]

    today = dt_date.today()
    day_start = datetime(today.year, today.month, today.day)
    day_end = datetime(today.year, today.month, today.day, 23, 59, 59)
    resolved_result = await db.execute(
        select(func.count(Case.id)).where(
            Case.status == "Closed",
            Case.updated_at >= day_start,
            Case.updated_at <= day_end,
        )
    )
    resolved_today = resolved_result.scalar_one() or 0

    return {
        "sla_breaching": len(sla_breaching),
        "awaiting_dev": len(awaiting_dev),
        "awaiting_customer": len(awaiting_customer),
        "resolved_today": resolved_today,
        "total_active": len(cases),
    }


@router.get("/by-ref/{jira_ref}", response_model=CaseDetailOut)
async def get_case_by_ref(jira_ref: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Case).where(Case.jira_ref == jira_ref).options(joinedload(Case.customer))
    )
    case = result.scalar_one_or_none()
    if not case:
        from app.services.jira import ensure_case_synced
        synced = await ensure_case_synced(db, jira_ref)
        if not synced:
            raise HTTPException(status_code=404, detail="Case not found")
        result = await db.execute(
            select(Case).where(Case.id == synced.id).options(joinedload(Case.customer))
        )
        case = result.scalar_one()

    log_result = await db.execute(
        select(AuditLog)
        .where(AuditLog.target_type == "case", AuditLog.target_id == jira_ref)
        .order_by(AuditLog.created_at.desc())
    )
    timeline = [
        CaseTimelineEntry(action=e.action, detail=e.detail, actor=e.actor, created_at=e.created_at)
        for e in log_result.scalars().all()
    ]

    related_cases: list[RelatedCaseSummary] = []
    related_refs = [r for r in (case.related_case_refs or "").split(",") if r]
    if related_refs:
        matched_result = await db.execute(
            select(Case).where(Case.jira_ref.in_(related_refs)).options(joinedload(Case.customer))
        )
        matched_by_ref = {c.jira_ref: c for c in matched_result.scalars().all()}
        for ref in related_refs:
            matched = matched_by_ref.get(ref)
            if matched:
                related_cases.append(RelatedCaseSummary(
                    jira_ref=ref, title=matched.title,
                    customer_name=matched.jira_customer_name or (matched.customer.name if matched.customer else None),
                    status=matched.status,
                ))
            else:
                related_cases.append(RelatedCaseSummary(jira_ref=ref))

    return CaseDetailOut(**_enrich(case), timeline=timeline, related_cases=related_cases)


@router.get("/by-ref/{jira_ref}/activity")
async def get_case_activity(jira_ref: str, db: AsyncSession = Depends(get_db)):
    """Real Jira comment/activity history for one ticket — separate from
    the AuditLog-backed Timeline above (Sedna Ops' own internal event
    trail, unchanged). Cached locally (see services/jira.py::
    fetch_case_activity()) keyed off the real local Case row, which is
    guaranteed to exist by the time this route is hit — the panel always
    calls GET /cases/by-ref/{jira_ref} (which runs ensure_case_synced())
    first. A missing row here means the panel was opened through some other
    path than the one that guarantees sync, so this 404s rather than
    silently falling back to a stateless fetch. Returns [] rather than an
    error on a transient fetch failure, so the tab shows a clean empty
    state instead of an error toast."""
    case_result = await db.execute(select(Case.id).where(Case.jira_ref == jira_ref))
    case_id = case_result.scalar_one_or_none()
    if case_id is None:
        raise HTTPException(status_code=404, detail="Case not synced locally yet")

    from app.services.jira import fetch_case_activity
    entries = await fetch_case_activity(db, case_id, jira_ref)
    return entries or []


@router.post("", response_model=CaseOut, status_code=201)
async def create_case(data: CaseCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Case).where(Case.jira_ref == data.jira_ref))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"A case for {data.jira_ref} already exists")
    case = Case(**data.model_dump())
    db.add(case)
    await db.commit()
    result = await db.execute(
        select(Case).where(Case.id == case.id).options(joinedload(Case.customer))
    )
    case = result.scalar_one()
    return CaseOut(**_enrich(case))


@router.patch("/{case_id}", response_model=CaseOut)
async def update_case(case_id: int, data: CaseUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Case).where(Case.id == case_id).options(joinedload(Case.customer))
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    payload = data.model_dump(exclude_none=True)

    escalate = payload.pop("escalate", None)
    if escalate is True:
        case.escalated_at = datetime.utcnow()
        db.add(AuditLog(actor="you", action="case.escalated", target_type="case", target_id=case.jira_ref, detail="manual"))
    elif escalate is False:
        case.escalated_at = None

    if payload.get("lane_override") == "":
        payload["lane_override"] = None

    if "status" in payload and payload["status"] != case.status:
        case.status_changed_at = datetime.utcnow()

    if payload.get("needs_csm_briefing") is True and not case.needs_csm_briefing:
        db.add(AuditLog(actor="you", action="case.csm_briefing", target_type="case", target_id=case.jira_ref))

    if "rovo_context" in payload:
        # Stamp/clear the companion timestamp — the client sends the text,
        # not a timestamp; "" (clearing the field) clears the timestamp too.
        case.rovo_context_at = datetime.utcnow() if payload["rovo_context"] else None

    for key, value in payload.items():
        setattr(case, key, value)

    await db.commit()
    await db.refresh(case)
    return CaseOut(**_enrich(case))
