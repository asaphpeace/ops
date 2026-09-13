from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.ai_observation import AiObservation

router = APIRouter(prefix="/ai-observations", tags=["ai-observations"])


def _enrich(o: AiObservation) -> dict:
    return {
        "id": o.id,
        "kind": o.kind,
        "summary": o.summary,
        "refs": o.refs,
        "customer_id": o.customer_id,
        "customer_name": o.customer.name if getattr(o, "customer", None) else None,
        "status": o.status,
        "model_used": o.model_used,
        "created_at": o.created_at,
        "reviewed_at": o.reviewed_at,
    }


@router.get("")
async def list_observations(status: str | None = None, db: AsyncSession = Depends(get_db)):
    """Advisory-only findings from the local Ollama supervisor. This
    endpoint, and the two below, are the ENTIRE surface of that feature —
    none of them can touch a Case/Upgrade/Customer/Incident row."""
    query = select(AiObservation).options(joinedload(AiObservation.customer)).order_by(AiObservation.created_at.desc())
    if status:
        query = query.where(AiObservation.status == status)
    result = await db.execute(query)
    return [_enrich(o) for o in result.scalars().all()]


@router.post("/{observation_id}/review")
async def review_observation(observation_id: int, db: AsyncSession = Depends(get_db)):
    obs = (await db.execute(select(AiObservation).where(AiObservation.id == observation_id))).scalar_one_or_none()
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    obs.status = "Reviewed"
    obs.reviewed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(obs)
    return _enrich(obs)


@router.post("/{observation_id}/dismiss")
async def dismiss_observation(observation_id: int, db: AsyncSession = Depends(get_db)):
    obs = (await db.execute(select(AiObservation).where(AiObservation.id == observation_id))).scalar_one_or_none()
    if not obs:
        raise HTTPException(status_code=404, detail="Observation not found")
    obs.status = "Dismissed"
    obs.reviewed_at = datetime.utcnow()
    await db.commit()
    await db.refresh(obs)
    return _enrich(obs)


@router.post("/recompute")
async def recompute_observations(db: AsyncSession = Depends(get_db)):
    """Manually triggers a real Ollama supervisor pass right now — the
    model is slow, so waiting for the next scheduled tick shouldn't be the
    only option."""
    from app.services.ollama_supervisor import run_supervisor_pass
    created = await run_supervisor_pass(db)
    return {"created": created}
