from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.case import Case
from app.models.customer import Customer
from app.schemas.case import CaseCreate, CaseUpdate, CaseOut

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
    awaiting_dev = [c for c in cases if c.status == "Awaiting Dev"]
    awaiting_customer = [c for c in cases if c.status == "Awaiting Customer"]

    return {
        "sla_breaching": len(sla_breaching),
        "awaiting_dev": len(awaiting_dev),
        "awaiting_customer": len(awaiting_customer),
        "resolved_today": 0,  # Phase 2: track resolved_at timestamp
        "total_active": len(cases),
    }


@router.post("", response_model=CaseOut, status_code=201)
async def create_case(data: CaseCreate, db: AsyncSession = Depends(get_db)):
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
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(case, key, value)
    await db.commit()
    await db.refresh(case)
    return CaseOut(**_enrich(case))
