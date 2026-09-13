from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.cancellation import Cancellation
from app.models.customer import Customer

router = APIRouter(prefix="/cancellations", tags=["cancellations"])

STAGES = ["Requested", "DevOps Notified", "Decommissioned"]


def _overdue(c: Cancellation) -> bool:
    """Overdue once past the effective date (end of the customer's yearly
    subscription) and infrastructure still hasn't been decommissioned."""
    return c.stage != "Decommissioned" and date.today() > c.effective_date


def _enrich(c: Cancellation) -> dict:
    d = {col.name: getattr(c, col.name) for col in c.__table__.columns}
    d["overdue"] = _overdue(c)
    d["days_until_effective"] = (c.effective_date - date.today()).days
    if c.customer:
        d["customer_name"] = c.customer.name
        d["customer_tier"] = c.customer.tier
        d["customer_arr_gbp"] = c.customer.arr_gbp
        d["customer_csm"] = c.customer.csm
    return d


@router.get("")
async def list_cancellations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Cancellation).options(joinedload(Cancellation.customer)).order_by(Cancellation.effective_date)
    )
    records = result.scalars().all()
    stage_order = {s: i for i, s in enumerate(STAGES)}
    # Overdue first within each stage — same priority-sort idea as SSO's overdue_days.
    records = sorted(records, key=lambda c: (stage_order.get(c.stage, 99), not _overdue(c)))
    return [_enrich(c) for c in records]


@router.post("", status_code=201)
async def create_cancellation(data: dict, db: AsyncSession = Depends(get_db)):
    """Log a cancellation a customer requested via email to Customer Success.
    Always treated as final — no retention/save-attempt stage."""
    customer_id = data.get("customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required")

    existing = await db.execute(select(Cancellation).where(Cancellation.customer_id == customer_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Customer already has a cancellation on record")

    customer = (await db.execute(select(Customer).where(Customer.id == customer_id))).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    effective_date_raw = data.get("effective_date")
    if effective_date_raw:
        try:
            effective_date = date.fromisoformat(effective_date_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="effective_date must be a valid date (YYYY-MM-DD)")
    elif customer.renewal_date:
        effective_date = customer.renewal_date
    else:
        raise HTTPException(
            status_code=400,
            detail="effective_date is required — this customer has no renewal_date on file to default to",
        )

    c = Cancellation(
        customer_id=customer_id,
        reason=data.get("reason"),
        jira_ref=data.get("jira_ref"),
        effective_date=effective_date,
        stage="Requested",
    )
    db.add(c)
    db.add(AuditLog(
        actor="system", action="cancellation.requested", target_type="customer",
        target_id=str(customer_id), detail=f"{customer.name} — effective {effective_date.isoformat()}",
    ))
    await db.commit()
    result = await db.execute(
        select(Cancellation).where(Cancellation.id == c.id).options(joinedload(Cancellation.customer))
    )
    return _enrich(result.scalar_one())


@router.patch("/{cancellation_id}")
async def update_cancellation(cancellation_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Cancellation).where(Cancellation.id == cancellation_id).options(joinedload(Cancellation.customer))
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Cancellation not found")

    new_stage = data.get("stage")
    for key, value in data.items():
        if hasattr(c, key) and key not in ("id", "customer_id"):
            setattr(c, key, value)

    if new_stage == "DevOps Notified" and c.devops_notified_at is None:
        c.devops_notified_at = datetime.utcnow()

    if new_stage == "Decommissioned":
        c.decommissioned_at = datetime.utcnow()
        if c.customer:
            c.customer.status = "Cancelled"
            db.add(AuditLog(
                actor="system", action="customer.cancelled", target_type="customer",
                target_id=str(c.customer_id), detail=f"{c.customer.name} — infrastructure decommissioned",
            ))

    await db.commit()
    await db.refresh(c)
    return _enrich(c)
