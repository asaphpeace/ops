from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.migration_priority import migration_priority

router = APIRouter(prefix="/migration-priority", tags=["migration-priority"])


@router.get("")
async def get_migration_priority(db: AsyncSession = Depends(get_db)):
    return await migration_priority(db)
