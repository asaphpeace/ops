from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.ops_note import OpsNote

router = APIRouter(prefix="/ops-notes", tags=["ops-notes"])


def _enrich(n: OpsNote) -> dict:
    return {
        "id": n.id,
        "text": n.text,
        "source_label": n.source_label,
        "customer_id": n.customer_id,
        "customer_name": n.customer.name if getattr(n, "customer", None) else None,
        "jira_ref": n.jira_ref,
        "created_at": n.created_at,
    }


@router.get("")
async def list_ops_notes(customer_id: int | None = None, jira_ref: str | None = None, db: AsyncSession = Depends(get_db)):
    query = select(OpsNote).options(joinedload(OpsNote.customer)).order_by(OpsNote.created_at.desc())
    if customer_id is not None:
        query = query.where(OpsNote.customer_id == customer_id)
    if jira_ref:
        query = query.where(OpsNote.jira_ref == jira_ref)
    result = await db.execute(query)
    return [_enrich(n) for n in result.scalars().all()]


@router.post("", status_code=201)
async def create_ops_note(data: dict, db: AsyncSession = Depends(get_db)):
    text = (data.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    note = OpsNote(
        text=text,
        source_label=(data.get("source_label") or "").strip() or None,
        customer_id=data.get("customer_id"),
        jira_ref=(data.get("jira_ref") or "").strip() or None,
    )
    db.add(note)
    await db.commit()
    # Plain refresh() only reloads the row's own columns — accessing the
    # lazy `customer` relationship afterward raises MissingGreenlet under
    # async SQLAlchemy. Explicitly ask refresh() to also load it.
    await db.refresh(note, attribute_names=["customer"])
    return _enrich(note)


@router.delete("/{note_id}", status_code=204)
async def delete_ops_note(note_id: int, db: AsyncSession = Depends(get_db)):
    note = (await db.execute(select(OpsNote).where(OpsNote.id == note_id))).scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    await db.delete(note)
    await db.commit()
