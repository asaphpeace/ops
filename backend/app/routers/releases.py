from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.release import Release
from app.schemas.release import ReleaseCreate, ReleaseOut

router = APIRouter(prefix="/releases", tags=["releases"])


@router.get("", response_model=list[ReleaseOut])
async def list_releases(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Release).order_by(Release.released_at.desc()))
    return result.scalars().all()


@router.get("/latest", response_model=ReleaseOut | None)
async def latest_release(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Release).where(Release.is_latest == True).order_by(Release.released_at.desc())
    )
    return result.scalar_one_or_none()


@router.post("", response_model=ReleaseOut, status_code=201)
async def create_release(data: ReleaseCreate, db: AsyncSession = Depends(get_db)):
    if data.is_latest:
        # Clear existing latest flag
        result = await db.execute(select(Release).where(Release.is_latest == True))
        for r in result.scalars().all():
            r.is_latest = False
    release = Release(**data.model_dump())
    db.add(release)
    await db.commit()
    await db.refresh(release)
    return release
