"""
Snapshot endpoints — manual digest trigger from the dashboard.

POST /snapshot/brief    → morning brief format
POST /snapshot/full     → full snapshot format

Both generate + post to Slack and return the text so the frontend
can show a preview before/after posting.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/snapshot", tags=["snapshot"])


@router.post("/brief")
async def trigger_brief():
    from app.services.digest import morning_brief
    text = await morning_brief()
    return {"text": text, "posted": True}


@router.post("/full")
async def trigger_full():
    from app.services.digest import full_snapshot
    text = await full_snapshot()
    return {"text": text, "posted": True}
