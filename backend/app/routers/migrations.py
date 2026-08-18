from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.migration_project import MigrationProject
from app.models.customer import Customer

router = APIRouter(prefix="/migrations", tags=["migrations"])

BOARD_STAGES = [
    "Not Started",
    "Assessed",
    "DevOps Priority",
    "Cust. Contacted",
    "Downtime Agreed",
    "In Progress",
    "Verifying",
    "Complete",
]

# Alias map to normalise any legacy/mismatched values stored before canonical list was locked
_STAGE_ALIAS = {
    "Customer Contacted": "Cust. Contacted",
    "Cust Contacted": "Cust. Contacted",
}


def _enrich(m: MigrationProject) -> dict:
    d = {col.name: getattr(m, col.name) for col in m.__table__.columns}
    d["stage"] = _STAGE_ALIAS.get(d["stage"], d["stage"])
    if m.customer:
        d["customer_name"] = m.customer.name
        d["customer_tier"] = m.customer.tier
        d["customer_infra"] = m.customer.infra
        d["customer_arr_gbp"] = m.customer.arr_gbp
        d["customer_renewal_date"] = m.customer.renewal_date.isoformat() if m.customer.renewal_date else None
    return d


@router.get("")
async def list_migrations(db: AsyncSession = Depends(get_db)):
    q = select(MigrationProject).options(joinedload(MigrationProject.customer)).order_by(MigrationProject.id)
    result = await db.execute(q)
    return [_enrich(m) for m in result.scalars().all()]


@router.get("/board")
async def migration_board(db: AsyncSession = Depends(get_db)):
    q = select(MigrationProject).options(joinedload(MigrationProject.customer))
    result = await db.execute(q)
    all_projects = result.scalars().all()

    by_stage: dict[str, list] = {s: [] for s in BOARD_STAGES}
    for m in all_projects:
        enriched = _enrich(m)
        stage = enriched["stage"]
        if stage not in by_stage:
            by_stage[stage] = []
        by_stage[stage].append(enriched)

    on_old = sum(1 for m in all_projects if m.customer and m.customer.infra in ("Old", "Mixed"))
    in_pipeline = sum(1 for m in all_projects if _STAGE_ALIAS.get(m.stage, m.stage) not in ("Not Started", "Complete"))
    needs_upgrade = sum(1 for m in all_projects if m.requires_upgrade)
    completed = sum(1 for m in all_projects if _STAGE_ALIAS.get(m.stage, m.stage) == "Complete")
    stalled = sum(1 for m in all_projects if m.stalled)

    return {
        "stages": by_stage,
        "stats": {
            "on_old_infra": on_old,
            "in_pipeline": in_pipeline,
            "needs_upgrade_first": needs_upgrade,
            "completed": completed,
            "stalled": stalled,
        },
    }


@router.patch("/{migration_id}")
async def update_migration(migration_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MigrationProject).where(MigrationProject.id == migration_id).options(joinedload(MigrationProject.customer))
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Migration not found")
    for key, value in data.items():
        if hasattr(m, key) and key not in ("id", "customer_id"):
            setattr(m, key, value)
    await db.commit()
    await db.refresh(m)
    return _enrich(m)
