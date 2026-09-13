"""Real, searchable browser over AuditLog — every write site in this app
already logs to this one table (case/upgrade/bug/incident/campaign/
migration/cancellation/customer transitions), but until now there was no
UI or endpoint to actually browse it; the only consumers were curated,
narrow slices (Command Center's "Since X" feed, a handful of per-entity
Timeline tabs). Confirmed live this was a real gap: diagnosing why a
cancelled Upgrade kept reappearing required raw SQL against this table,
not anything reachable from the app itself. Read-only — this router never
writes."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/audit-log", tags=["audit-log"])

_MAX_LIMIT = 500


def _row_out(r: AuditLog) -> dict:
    return {
        "id": r.id,
        "actor": r.actor,
        "action": r.action,
        "target_type": r.target_type,
        "target_id": r.target_id,
        "detail": r.detail,
        "created_at": r.created_at,
    }


@router.get("")
async def list_audit_log(
    q: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    before: datetime | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """`q` matches (case-insensitively) against target_id OR detail — the
    two free-text fields most searches are actually about ("DSD-31489",
    "Peak People"). `before` pages backward from a prior page's oldest
    `created_at` ("load older") rather than an offset, since this table is
    written to continuously by live poll cycles — an offset-based page
    would silently skip or repeat rows as new entries land underneath it."""
    limit = max(1, min(limit, _MAX_LIMIT))
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if q:
        like = f"%{q}%"
        query = query.where((AuditLog.target_id.ilike(like)) | (AuditLog.detail.ilike(like)))
    if action:
        query = query.where(AuditLog.action == action)
    if target_type:
        query = query.where(AuditLog.target_type == target_type)
    if before:
        query = query.where(AuditLog.created_at < before)

    rows = (await db.execute(query)).scalars().all()
    return {"rows": [_row_out(r) for r in rows]}


@router.get("/actions")
async def list_actions(db: AsyncSession = Depends(get_db)):
    """Every distinct `action` value ever logged — feeds the filter
    dropdown with real values instead of a hand-maintained, inevitably
    stale list of every action string this app has ever grown."""
    result = await db.execute(select(AuditLog.action).distinct().order_by(AuditLog.action))
    return {"actions": [row[0] for row in result.all()]}
