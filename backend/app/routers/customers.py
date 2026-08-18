from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.customer import Customer
from app.schemas.customer import CustomerOut, CustomerDetail, CustomerCreate, CustomerUpdate

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerOut])
async def list_customers(
    tier: str | None = None,
    csm: str | None = None,
    infra: str | None = None,
    health_max: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Customer)
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
    result = await db.execute(select(Customer))
    customers = result.scalars().all()

    arr_old_infra = sum(c.arr_gbp for c in customers if c.infra == "Old")
    arr_red_health = sum(c.arr_gbp for c in customers if c.health_score <= 45)
    arr_renewal_risk = sum(
        c.arr_gbp for c in customers
        if c.health_score <= 70 and c.renewal_date and
        (c.renewal_date.toordinal() - __import__("datetime").date.today().toordinal()) <= 60
    )

    arr_open_defects = 0  # Phase 2 — join with open defect cases

    return {
        "total": len(customers),
        "arr_old_infra": arr_old_infra,
        "arr_red_health": arr_red_health,
        "arr_renewal_risk": arr_renewal_risk,
        "arr_open_defects": arr_open_defects,
        "old_infra_count": sum(1 for c in customers if c.infra == "Old"),
        "red_health_count": sum(1 for c in customers if c.health_score <= 45),
    }


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


@router.post("", response_model=CustomerOut, status_code=201)
async def create_customer(data: CustomerCreate, db: AsyncSession = Depends(get_db)):
    customer = Customer(**data.model_dump())
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
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(customer, key, value)
    await db.commit()
    await db.refresh(customer)
    return customer
