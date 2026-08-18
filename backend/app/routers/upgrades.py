from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.upgrade import Upgrade
from app.models.customer import Customer
from app.schemas.upgrade import UpgradeCreate, UpgradeUpdate, UpgradeOut

router = APIRouter(prefix="/upgrades", tags=["upgrades"])

PIPELINE_STAGES = [
    "Requested",
    "DevOps Approval",
    "Cust. Confirmed",
    "Scheduled",
    "In Progress",
    "Verified Done",
]


def _enrich(u: Upgrade) -> dict:
    d = {col.name: getattr(u, col.name) for col in u.__table__.columns}
    if u.customer:
        d["customer_name"] = u.customer.name
        d["customer_tier"] = u.customer.tier
    return d


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
    return [UpgradeOut(**_enrich(u)) for u in result.scalars().all()]


@router.get("/pipeline")
async def pipeline_summary(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Upgrade)
        .where(Upgrade.stage != "Verified Done")
        .options(joinedload(Upgrade.customer))
    )
    upgrades = result.scalars().all()

    by_stage: dict[str, list] = {s: [] for s in PIPELINE_STAGES}
    for u in upgrades:
        if u.stage in by_stage:
            by_stage[u.stage].append(_enrich(u))

    blocked_count = sum(1 for u in upgrades if u.blocked)
    unconfirmed = sum(1 for u in upgrades if u.stage == "Cust. Confirmed" and not u.confirmed_at)

    done_q = await db.execute(
        select(Upgrade).where(Upgrade.stage == "Verified Done")
    )
    done_count = len(done_q.scalars().all())

    return {
        "stages": by_stage,
        "active_total": len(upgrades),
        "blocked": blocked_count,
        "unconfirmed_slots": unconfirmed,
        "done_this_month": done_count,
    }


@router.post("", response_model=UpgradeOut, status_code=201)
async def create_upgrade(data: UpgradeCreate, db: AsyncSession = Depends(get_db)):
    upgrade = Upgrade(**data.model_dump())
    db.add(upgrade)
    await db.commit()
    result = await db.execute(
        select(Upgrade).where(Upgrade.id == upgrade.id).options(joinedload(Upgrade.customer))
    )
    u = result.scalar_one()
    return UpgradeOut(**_enrich(u))


@router.patch("/{upgrade_id}", response_model=UpgradeOut)
async def update_upgrade(upgrade_id: int, data: UpgradeUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Upgrade).where(Upgrade.id == upgrade_id).options(joinedload(Upgrade.customer))
    )
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Upgrade not found")
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(u, key, value)
    await db.commit()
    await db.refresh(u)
    return UpgradeOut(**_enrich(u))
