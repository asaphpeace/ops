from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.troubleshoot import investigate

router = APIRouter(prefix="/troubleshoot", tags=["troubleshoot"])


@router.post("/investigate")
async def investigate_endpoint(data: dict, db: AsyncSession = Depends(get_db)):
    query = (data.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "query is required")
    return await investigate(db, query)
