"""
Bug/Defect Intelligence — bridges DSD support tickets to the real VMS
dev-project bugs they're linked to, and rolls up which customers are
affected by each bug.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.vms_bug import VmsBug
from app.services.bug_linkage import cases_by_bug_ref
from app.services.digest import summarize_bug_impact

router = APIRouter(prefix="/bugs", tags=["bugs"])

# VMS priority sampled as uniformly "Severity 3" in a live check — not a
# trustworthy triage signal. DSD's own Severity (the customer-facing
# urgency) stays authoritative wherever the two would disagree, so VMS
# priority is deliberately never surfaced here.


def _case_summary(c: Case) -> dict:
    return {
        "jira_ref": c.jira_ref,
        "title": c.title,
        "priority": c.priority,
        "days_open": c.days_open,
        "customer_name": c.jira_customer_name or (c.customer.name if c.customer else None),
        "customer_tier": c.customer.tier if c.customer else None,
    }


def _bug_out(bug: VmsBug, linked: list[Case]) -> dict:
    customers = sorted({c.jira_customer_name or (c.customer.name if c.customer else "Unknown") for c in linked})
    return {
        "jira_ref": bug.jira_ref,
        "issue_type": bug.issue_type,
        "status": bug.status,
        "fix_version": bug.fix_version,
        "sprint_name": bug.sprint_name,
        "sprint_state": bug.sprint_state,
        "assignee": bug.assignee,
        "labels": [l for l in (bug.labels or "").split(",") if l],
        "affected_customers": customers,
        "linked_cases": [_case_summary(c) for c in linked],
        "ai_summary": bug.ai_summary,
        "ai_summary_at": bug.ai_summary_at,
        "rovo_context": bug.rovo_context,
        "rovo_context_at": bug.rovo_context_at,
    }


@router.get("")
async def list_bugs(db: AsyncSession = Depends(get_db)):
    bugs = (await db.execute(select(VmsBug))).scalars().all()
    by_bug = await cases_by_bug_ref(db)

    out = [_bug_out(bug, by_bug.get(bug.jira_ref, [])) for bug in bugs]
    out.sort(key=lambda b: len(b["affected_customers"]), reverse=True)
    return out


@router.get("/{jira_ref}")
async def get_bug(jira_ref: str, db: AsyncSession = Depends(get_db)):
    bug = (await db.execute(select(VmsBug).where(VmsBug.jira_ref == jira_ref))).scalar_one_or_none()
    if not bug:
        raise HTTPException(status_code=404, detail="Bug not found")

    linked = (await cases_by_bug_ref(db, {jira_ref})).get(jira_ref, [])
    return _bug_out(bug, linked)


@router.patch("/{jira_ref}")
async def update_bug(jira_ref: str, data: dict, db: AsyncSession = Depends(get_db)):
    """Narrow, single-purpose PATCH — currently only rovo_context, so a
    plain dict body (matching routers/vms_sandbox.py's precedent) rather
    than a new Pydantic schema class for one field. The only write path
    VmsBug has today."""
    bug = (await db.execute(select(VmsBug).where(VmsBug.jira_ref == jira_ref))).scalar_one_or_none()
    if not bug:
        raise HTTPException(status_code=404, detail="Bug not found")

    if "rovo_context" in data:
        bug.rovo_context = data["rovo_context"] or None
        bug.rovo_context_at = datetime.utcnow() if data["rovo_context"] else None
        await db.commit()

    linked = (await cases_by_bug_ref(db, {jira_ref})).get(jira_ref, [])
    return _bug_out(bug, linked)


@router.get("/{jira_ref}/timeline")
async def bug_timeline(jira_ref: str, db: AsyncSession = Depends(get_db)):
    """Lifecycle history for a bug — status/sprint transitions written by
    _sync_vms_bug() at poll time. Starts empty for any bug that existed
    before this was added; only tracks transitions going forward."""
    bug = (await db.execute(select(VmsBug).where(VmsBug.jira_ref == jira_ref))).scalar_one_or_none()
    if not bug:
        raise HTTPException(status_code=404, detail="Bug not found")

    log_result = await db.execute(
        select(AuditLog)
        .where(AuditLog.target_type == "bug", AuditLog.target_id == jira_ref)
        .order_by(AuditLog.created_at.desc())
    )
    return [
        {"action": e.action, "detail": e.detail, "actor": e.actor, "created_at": e.created_at}
        for e in log_result.scalars().all()
    ]


@router.post("/{jira_ref}/summarize")
async def summarize_bug(jira_ref: str, db: AsyncSession = Depends(get_db)):
    """On-demand AI summary of the common thread across affected customers. Cached."""
    bug = (await db.execute(select(VmsBug).where(VmsBug.jira_ref == jira_ref))).scalar_one_or_none()
    if not bug:
        raise HTTPException(status_code=404, detail="Bug not found")

    if not settings.ai_enabled:
        return {"summary": None, "message": "ANTHROPIC_API_KEY not set — AI summaries disabled"}

    linked = (await cases_by_bug_ref(db, {jira_ref})).get(jira_ref, [])
    customers = sorted({c.jira_customer_name or "Unknown" for c in linked})
    summary = await summarize_bug_impact(jira_ref, customers, linked, db)
    bug.ai_summary = summary
    bug.ai_summary_at = datetime.utcnow()
    await db.commit()
    return {"summary": summary, "generated_at": bug.ai_summary_at}
