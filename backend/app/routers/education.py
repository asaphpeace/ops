from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.training import TrainingGap, TrainingSession
from app.models.customer import Customer

router = APIRouter(prefix="/education", tags=["education"])


def _enrich_gap(g: TrainingGap) -> dict:
    d = {col.name: getattr(g, col.name) for col in g.__table__.columns}
    if g.customer:
        d["customer_name"] = g.customer.name
        d["customer_tier"] = g.customer.tier
    return d


def _enrich_session(s: TrainingSession) -> dict:
    d = {col.name: getattr(s, col.name) for col in s.__table__.columns}
    if s.customer:
        d["customer_name"] = s.customer.name
        d["customer_tier"] = s.customer.tier
        d["customer_csm"] = s.customer.csm
    return d


@router.get("/gaps")
async def list_gaps(db: AsyncSession = Depends(get_db)):
    q = select(TrainingGap).options(joinedload(TrainingGap.customer)).order_by(TrainingGap.logged_at.desc())
    result = await db.execute(q)
    return [_enrich_gap(g) for g in result.scalars().all()]


@router.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    q = select(TrainingSession).options(joinedload(TrainingSession.customer)).order_by(TrainingSession.session_date.desc())
    result = await db.execute(q)
    return [_enrich_session(s) for s in result.scalars().all()]


@router.get("/stats")
async def education_stats(db: AsyncSession = Depends(get_db)):
    gaps_result = await db.execute(
        select(TrainingGap).options(joinedload(TrainingGap.customer))
    )
    gaps = gaps_result.scalars().all()

    sessions_result = await db.execute(select(TrainingSession))
    sessions = sessions_result.scalars().all()

    area_counts: dict[str, int] = {}
    for g in gaps:
        area_counts[g.area] = area_counts.get(g.area, 0) + g.count

    top_areas = sorted(area_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    follow_ups = sum(1 for s in sessions if s.follow_up_needed)

    return {
        "total_gaps": sum(g.count for g in gaps),
        "unique_areas": len(area_counts),
        "total_sessions": len(sessions),
        "follow_ups_due": follow_ups,
        "top_areas": [{"area": a, "count": c} for a, c in top_areas],
    }
