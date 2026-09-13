import re
from datetime import date as dt_date
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.customer_tenant_info import CustomerTenantInfo
from app.models.release import Release
from app.models.training import TrainingGap, TrainingSession
from app.models.customer import Customer
from app.services.release_notes import master_releases_between, refresh_release_notes_cache
from app.services.training_priority import training_recommendations

router = APIRouter(prefix="/education", tags=["education"])


class SessionCreate(BaseModel):
    customer_id: int
    session_date: dt_date
    topic_area: str
    format: Optional[str] = None
    delivered_by: str = "Asaph"
    outcome: Optional[str] = None
    follow_up_needed: bool = False
    follow_up_text: Optional[str] = None


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


@router.post("/sessions", status_code=201)
async def create_session(body: SessionCreate, db: AsyncSession = Depends(get_db)):
    session = TrainingSession(**body.model_dump())
    db.add(session)
    await db.commit()
    await db.refresh(session)
    result = await db.execute(
        select(TrainingSession).options(joinedload(TrainingSession.customer)).where(TrainingSession.id == session.id)
    )
    return _enrich_session(result.scalar_one())


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


@router.get("/training-recommendations")
async def get_training_recommendations(db: AsyncSession = Depends(get_db)):
    return await training_recommendations(db)


@router.post("/refresh-release-notes")
async def refresh_release_notes(db: AsyncSession = Depends(get_db)):
    """On-demand ingestion — real, incremental (only fetches versions with
    zero cached rows, see refresh_release_notes_cache()'s own docstring),
    so repeat calls are cheap. Range is derived from real data: every real
    customer's current PROD version up to the current latest Release."""
    latest = (await db.execute(select(Release).where(Release.is_latest == True))).scalar_one_or_none()  # noqa: E712
    if not latest:
        return {"already_cached": [], "fetched": [], "empty": [], "failed": [], "note": "No latest Release on file"}

    prod_versions = (
        await db.execute(
            select(CustomerTenantInfo.release).where(
                CustomerTenantInfo.environment == "PROD", CustomerTenantInfo.release.isnot(None),
            )
        )
    ).scalars().all()
    if not prod_versions:
        return {"already_cached": [], "fetched": [], "empty": [], "failed": [], "note": "No real customer version data on file"}

    oldest = min(prod_versions, key=lambda v: tuple(int(x) for x in re.findall(r"\d+", v)[:2]))
    versions = master_releases_between(oldest, latest.version)
    return await refresh_release_notes_cache(db, versions)
