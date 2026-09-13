from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.migration_project import MigrationProject
from app.models.customer import Customer
from app.models.customer_tenant_info import CustomerTenantInfo

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
        d["customer_prod_version"] = m.customer.prod_version
    return d


@router.get("")
async def list_migrations(db: AsyncSession = Depends(get_db)):
    q = select(MigrationProject).options(joinedload(MigrationProject.customer)).order_by(MigrationProject.id)
    result = await db.execute(q)
    return [_enrich(m) for m in result.scalars().all()]


@router.post("", status_code=201)
async def create_migration(data: dict, db: AsyncSession = Depends(get_db)):
    """Kick off a migration batch for a customer not yet in the pipeline."""
    customer_id = data.get("customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required")

    existing = await db.execute(
        select(MigrationProject).where(MigrationProject.customer_id == customer_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Customer already has a migration in progress")

    m = MigrationProject(
        customer_id=customer_id,
        stage="Not Started",
        complexity=data.get("complexity", "Medium"),
        # A human explicitly chose to start this one right now — goes
        # straight into the kanban, not the Migration Priority backlog
        # (that backlog is for bulk-imported candidates no one has acted
        # on yet, e.g. Elias's Old-AWS environment list).
        initiated_at=datetime.utcnow(),
    )
    db.add(m)
    await db.flush()
    db.add(AuditLog(actor="you", action="migration.created", target_type="customer", target_id=str(customer_id)))
    await db.commit()
    result = await db.execute(
        select(MigrationProject).where(MigrationProject.id == m.id).options(joinedload(MigrationProject.customer))
    )
    return _enrich(result.scalar_one())


@router.get("/board")
async def migration_board(db: AsyncSession = Depends(get_db)):
    q = select(MigrationProject).options(joinedload(MigrationProject.customer))
    result = await db.execute(q)
    all_projects = result.scalars().all()

    # Only initiated migrations ever appear on the kanban — a bulk-imported
    # candidate (initiated_at is NULL) sits in the Migration Priority
    # backlog below until a human explicitly clicks "Initiate", so "Not
    # Started" never turns into a long dumping ground of un-actioned rows.
    initiated = [m for m in all_projects if m.initiated_at is not None]
    candidates = [m for m in all_projects if m.initiated_at is None]

    by_stage: dict[str, list] = {s: [] for s in BOARD_STAGES}
    for m in initiated:
        enriched = _enrich(m)
        stage = enriched["stage"]
        if stage not in by_stage:
            by_stage[stage] = []
        by_stage[stage].append(enriched)

    # Elias's formula, made visible instead of something to figure out per
    # customer: `requires_upgrade` is already stored on the row from the
    # original import; `has_test_dev` is derived here from the real
    # per-environment tenant-info rows so a candidate's card can show
    # "Upgrade first" / "Easy win" and "Has TEST/DEV" at a glance.
    candidate_customer_ids = [m.customer_id for m in candidates]
    test_dev_ids: set[int] = set()
    if candidate_customer_ids:
        test_dev_ids = set((await db.execute(
            select(CustomerTenantInfo.customer_id)
            .where(
                CustomerTenantInfo.customer_id.in_(candidate_customer_ids),
                CustomerTenantInfo.environment.in_(("TEST", "DEV")),
            )
            .distinct()
        )).scalars().all())

    candidate_rows = []
    for m in candidates:
        enriched = _enrich(m)
        enriched["has_test_dev"] = m.customer_id in test_dev_ids
        candidate_rows.append(enriched)
    # Easy Wins first, then Upgrade-First — matches Elias's own framing of
    # "migrate the simple ones first" — then bigger accounts within each.
    candidate_rows.sort(key=lambda r: (r["requires_upgrade"], -(r["customer_arr_gbp"] or 0)))

    on_old = sum(1 for m in all_projects if m.customer and m.customer.infra in ("Old", "Mixed"))
    needs_upgrade = sum(1 for m in all_projects if m.requires_upgrade)
    in_pipeline = sum(1 for m in initiated if _STAGE_ALIAS.get(m.stage, m.stage) not in ("Not Started", "Complete"))
    completed = sum(1 for m in initiated if _STAGE_ALIAS.get(m.stage, m.stage) == "Complete")
    stalled = sum(1 for m in initiated if m.stalled)

    return {
        "stages": by_stage,
        "candidates": candidate_rows,
        "stats": {
            "on_old_infra": on_old,
            "in_pipeline": in_pipeline,
            "needs_upgrade_first": needs_upgrade,
            "completed": completed,
            "stalled": stalled,
            "candidates_count": len(candidate_rows),
        },
    }


@router.post("/{migration_id}/initiate")
async def initiate_migration(migration_id: int, db: AsyncSession = Depends(get_db)):
    """Move a not-yet-started candidate from the Migration Priority backlog
    into the active kanban pipeline (stays at whatever `stage` it's already
    at — normally the literal "Not Started" first column)."""
    result = await db.execute(
        select(MigrationProject).where(MigrationProject.id == migration_id).options(joinedload(MigrationProject.customer))
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Migration not found")
    if m.initiated_at is None:
        m.initiated_at = datetime.utcnow()
        db.add(AuditLog(actor="you", action="migration.initiated", target_type="customer", target_id=str(m.customer_id)))
        await db.commit()
        await db.refresh(m)
    return _enrich(m)


# Keeps Customer.infra honest against real migration progress instead of
# letting it drift (found live: 25 of 35 tracked customers showed "New"
# infra while their migration was still "Not Started"/"Assessed" — nothing
# had actually cut over). Only "Complete" means the customer is truly on
# new infra; "In Progress"/"Verifying" are mid-cutover ("Mixed"); every
# earlier stage means they're still fully on old infra.
def _infra_for_stage(stage: str) -> str:
    if stage == "Complete":
        return "New"
    if stage in ("In Progress", "Verifying"):
        return "Mixed"
    return "Old"


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
    if "stage" in data and m.customer:
        m.customer.infra = _infra_for_stage(_STAGE_ALIAS.get(m.stage, m.stage))
    await db.commit()
    await db.refresh(m)
    return _enrich(m)
