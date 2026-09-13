from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.customer import Customer

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _customer_ids(c: Campaign) -> list[int]:
    return [int(v) for v in c.customer_ids.split(",") if v]


def _enrich(c: Campaign) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "message": c.message,
        "status": c.status,
        "customer_count": len(_customer_ids(c)),
        "incident_id": c.incident_id,
        "created_at": c.created_at,
        "sent_at": c.sent_at,
    }


@router.get("")
async def list_campaigns(incident_id: int | None = Query(default=None), db: AsyncSession = Depends(get_db)):
    query = select(Campaign).order_by(Campaign.created_at.desc())
    if incident_id is not None:
        query = query.where(Campaign.incident_id == incident_id)
    result = await db.execute(query)
    return [_enrich(c) for c in result.scalars().all()]


@router.post("", status_code=201)
async def create_campaign(data: dict, db: AsyncSession = Depends(get_db)):
    name = data.get("name")
    customer_ids = data.get("customer_ids") or []
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not customer_ids:
        raise HTTPException(status_code=400, detail="customer_ids must be a non-empty list")

    campaign = Campaign(
        name=name,
        message=data.get("message", ""),
        customer_ids=",".join(str(cid) for cid in customer_ids),
        incident_id=data.get("incident_id"),
        status="Draft",
    )
    db.add(campaign)
    await db.flush()
    db.add(AuditLog(
        actor="you", action="campaign.created", target_type="campaign",
        target_id=str(campaign.id), detail=f"{name} — {len(customer_ids)} customers",
    ))
    await db.commit()
    await db.refresh(campaign)
    return _enrich(campaign)


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    campaign = (await db.execute(select(Campaign).where(Campaign.id == campaign_id))).scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    ids = _customer_ids(campaign)
    customers = (await db.execute(select(Customer).where(Customer.id.in_(ids)))).scalars().all()
    customers_by_id = {c.id: c for c in customers}

    out = _enrich(campaign)
    out["customers"] = [
        {"id": cid, "name": customers_by_id[cid].name if cid in customers_by_id else None}
        for cid in ids
    ]
    return out


@router.patch("/{campaign_id}")
async def update_campaign(campaign_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    campaign = (await db.execute(select(Campaign).where(Campaign.id == campaign_id))).scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status == "Sent" and any(k in data for k in ("name", "message", "customer_ids")):
        raise HTTPException(status_code=400, detail="A sent campaign's content can't be edited")

    new_status = data.get("status")
    for key, value in data.items():
        if key == "customer_ids":
            campaign.customer_ids = ",".join(str(cid) for cid in value)
        elif hasattr(campaign, key) and key not in ("id", "created_at"):
            setattr(campaign, key, value)

    if new_status == "Sent" and campaign.sent_at is None:
        campaign.sent_at = datetime.utcnow()
        db.add(AuditLog(
            actor="you", action="campaign.sent", target_type="campaign",
            target_id=str(campaign.id), detail=campaign.name,
        ))

    await db.commit()
    await db.refresh(campaign)
    return _enrich(campaign)
