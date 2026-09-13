from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.case import Case
from app.models.customer import Customer
from app.models.jira_unmatched import JiraUnmatched
from app.services import jira as jira_service

router = APIRouter(prefix="/jira", tags=["jira"])


@router.get("/unmatched")
async def list_unmatched(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(JiraUnmatched)
        .where(JiraUnmatched.dismissed == False)  # noqa: E712
        .order_by(JiraUnmatched.last_seen_at.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "jira_ref": r.jira_ref,
            "title": r.title,
            "issue_type": r.issue_type,
            "case_type": r.case_type,
            "priority": r.priority,
            "labels": r.labels.split(",") if r.labels else [],
            "days_open": r.days_open,
            "jira_customer_name": r.jira_customer_name,
            "request_type": r.request_type,
            "first_seen_at": r.first_seen_at.date().isoformat(),
            "last_seen_at": r.last_seen_at.date().isoformat(),
        }
        for r in rows
    ]


class AssignBody(BaseModel):
    customer_id: int
    title: str
    case_type: str
    environment: str = "PROD"


@router.post("/unmatched/{jira_ref}/assign")
async def assign_unmatched(jira_ref: str, body: AssignBody, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(JiraUnmatched).where(JiraUnmatched.jira_ref == jira_ref))
    unmatched = result.scalar_one_or_none()
    if not unmatched:
        raise HTTPException(404, "Unmatched ref not found")

    customer_res = await db.execute(select(Customer).where(Customer.id == body.customer_id))
    customer = customer_res.scalar_one_or_none()
    if not customer:
        raise HTTPException(404, "Customer not found")

    existing_case = await db.execute(select(Case).where(Case.jira_ref == jira_ref))
    if existing_case.scalar_one_or_none():
        raise HTTPException(409, f"A case for {jira_ref} already exists — this unmatched row is stale")

    case = Case(
        customer_id=body.customer_id,
        jira_ref=jira_ref,
        title=body.title,
        case_type=body.case_type,
        environment=body.environment,
        status="Active",
        priority=unmatched.priority,
        days_open=unmatched.days_open,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(case)
    await db.delete(unmatched)
    await db.commit()

    return {"status": "assigned", "jira_ref": jira_ref, "customer": customer.name}


@router.delete("/unmatched/{jira_ref}")
async def dismiss_unmatched(jira_ref: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(JiraUnmatched).where(JiraUnmatched.jira_ref == jira_ref))
    unmatched = result.scalar_one_or_none()
    if not unmatched:
        raise HTTPException(404, "Unmatched ref not found")
    unmatched.dismissed = True
    await db.commit()
    return {"status": "dismissed", "jira_ref": jira_ref}


@router.post("/poll")
async def trigger_poll():
    """Manually trigger a Jira poll (useful for testing without waiting for the scheduler)."""
    result = await jira_service.poll_and_upsert()
    return result
