"""Browse/manage knowledge mined from Slack context by the local Ollama
model — services/knowledge_extraction.py. Extraction itself always runs as
a background task (never blocks a request): a full pass over many/large
notes is a genuinely slow, sequential-by-nature job (one local Ollama
server, no concurrency benefit) — see extract_now() below."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.models.knowledge_extract import KnowledgeExtract

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _enrich(k: KnowledgeExtract) -> dict:
    note = getattr(k, "source_note", None)
    return {
        "id": k.id,
        "category": k.category,
        "summary": k.summary,
        "source_note_id": k.source_note_id,
        "source_label": note.source_label if note else None,
        "customer_id": note.customer_id if note else None,
        "jira_ref": note.jira_ref if note else None,
        "model_used": k.model_used,
        "dismissed": k.dismissed,
        "created_at": k.created_at,
    }


@router.get("")
async def list_knowledge(
    category: str | None = None,
    include_dismissed: bool = False,
    db: AsyncSession = Depends(get_db),
):
    query = select(KnowledgeExtract).options(joinedload(KnowledgeExtract.source_note)).order_by(
        KnowledgeExtract.created_at.desc()
    )
    if category:
        query = query.where(KnowledgeExtract.category == category)
    if not include_dismissed:
        query = query.where(KnowledgeExtract.dismissed.is_(False))
    result = await db.execute(query)
    return [_enrich(k) for k in result.scalars().all()]


@router.post("/{extract_id}/dismiss")
async def dismiss_extract(extract_id: int, db: AsyncSession = Depends(get_db)):
    extract = (
        await db.execute(select(KnowledgeExtract).where(KnowledgeExtract.id == extract_id))
    ).scalar_one_or_none()
    if not extract:
        raise HTTPException(status_code=404, detail="Extract not found")
    extract.dismissed = True
    await db.commit()
    await db.refresh(extract)
    return {"id": extract.id, "dismissed": extract.dismissed}


async def _run_extraction_task():
    from app.services.knowledge_extraction import run_knowledge_extraction

    async with AsyncSessionLocal() as db:
        created = await run_knowledge_extraction(db)
    logger.info("Knowledge extraction (manual trigger) finished: %d new extract(s)", created)


@router.post("/extract-now")
async def extract_now():
    """Fires the extraction pass as a background task and returns
    immediately — a full pass can take many minutes (each note is chunked
    and each chunk is its own sequential Ollama call), far past any
    reasonable request timeout. Check GET /knowledge again after a few
    minutes rather than waiting on this response."""
    asyncio.create_task(_run_extraction_task())
    return {"started": True}
