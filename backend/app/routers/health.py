from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.config import settings
from app.database import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health():
    return {
        "status": "ok",
        "service": "sedna-ops-api",
        "auth_enabled": settings.auth_enabled,
        "jira_base_url": settings.jira_base_url,
    }


@router.get("/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}
