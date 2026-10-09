"""One merged, newest-first activity timeline per customer — the full-page
customer profile's Activity tab. Pulls together everything that happened to
or about a customer that otherwise lives in separate places: manual notes,
ops notes, comms campaigns, cases raised/resolved, escalations, upgrades,
Upgrade Runner automations, training sessions and relevant audit events.

Read-only. Each item has a `kind` so the UI can filter (Notes, Comms,
Cases, Escalations, Upgrades, Automation, Training, System)."""
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.automation_run import AutomationRun
from app.models.campaign import Campaign
from app.models.case import Case
from app.models.customer import Customer
from app.models.note import CustomerNote
from app.models.ops_note import OpsNote
from app.models.training import TrainingSession
from app.models.upgrade import Upgrade

router = APIRouter(prefix="/customers", tags=["customers"])

_MAX_ITEMS = 500
# Background bookkeeping, not something a person did or needs to see —
# these two alone are ~35k of the ~35k customer-targeted audit rows.
_AUDIT_NOISE = {"upgrade.duplicate_suppressed", "upgrade.already_satisfied_skipped"}
_CASE_AUDIT_KIND = {"case.escalated": "escalation", "case.high_priority": "escalation", "case.status_changed": "case"}


def _item(kind: str, when: datetime | date | None, title: str, detail: str | None = None,
          ref: str | None = None, actor: str | None = None, **extra) -> dict | None:
    if when is None:
        return None
    if isinstance(when, date) and not isinstance(when, datetime):
        when = datetime.combine(when, time(12, 0), tzinfo=timezone.utc)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    # extra: link (in-app route), note_id/is_sticky (pin toggle), flag
    # (short status pill, e.g. "follow-up").
    return {"kind": kind, "when": when, "title": title, "detail": detail, "ref": ref, "actor": actor,
            "link": extra.get("link"), "note_id": extra.get("note_id"), "is_sticky": extra.get("is_sticky"),
            "flag": extra.get("flag")}


@router.get("/{customer_id}/activity")
async def customer_activity(customer_id: int, db: AsyncSession = Depends(get_db)):
    if not await db.get(Customer, customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")
    items: list[dict | None] = []

    for n in (await db.execute(select(CustomerNote).where(CustomerNote.customer_id == customer_id))).scalars():
        items.append(_item("note", n.created_at, "Note", n.text, actor=n.author, note_id=n.id, is_sticky=n.is_sticky))
    for n in (await db.execute(select(OpsNote).where(OpsNote.customer_id == customer_id))).scalars():
        items.append(_item("note", n.created_at, f"Ops note{' · ' + n.source_label if n.source_label else ''}", n.text, ref=n.jira_ref))

    target = str(customer_id)
    for c in (await db.execute(select(Campaign))).scalars():
        if target in (c.customer_ids or "").split(","):
            items.append(_item("comms", c.sent_at or c.created_at, f"Campaign {'sent' if c.sent_at else 'drafted'}: {c.name}",
                               link=f"/customers/comms?campaign={c.id}", flag=c.status))

    cases = (await db.execute(select(Case).where(Case.customer_id == customer_id))).scalars().all()
    refs = {c.jira_ref for c in cases}
    title_by_ref = {c.jira_ref: c.title for c in cases}
    for c in cases:
        items.append(_item("case", c.created_at, f"Case raised — {c.title}", f"{c.priority} priority", ref=c.jira_ref))
        if c.resolved_at:
            items.append(_item("case", c.resolved_at, f"Case resolved — {c.title}", c.status, ref=c.jira_ref))
        if c.escalated_at:
            items.append(_item("escalation", c.escalated_at, f"Escalated — {c.title}", None, ref=c.jira_ref))

    for u in (await db.execute(select(Upgrade).where(Upgrade.customer_id == customer_id))).scalars():
        span = f"{u.environment} {u.from_version or '?'} → {u.to_version}"
        items.append(_item("upgrade", u.created_at, f"Upgrade requested · {span}", u.stage, ref=u.jira_ref))
        if u.scheduled_at:
            items.append(_item("upgrade", u.scheduled_at, f"Upgrade scheduled · {span}", None, ref=u.jira_ref))
        done = u.date_done or (u.verified_at if u.stage == "Verified Done" else None)
        if done:
            items.append(_item("upgrade", done, f"Upgrade done · {span}", u.stage, ref=u.jira_ref))

    for r in (await db.execute(select(AutomationRun).where(AutomationRun.customer_id == customer_id))).scalars():
        label = "ECR check" if r.kind == "ecr_tag_check" else ("Dry-run" if r.dry_run else "Upgrade run")
        detail = f"{r.status}" + (f" · post-check {r.post_check_release}" if r.post_check_release else "")
        items.append(_item("automation", r.started_at, f"{label} · {r.environment} → {r.target_version}", detail, actor=r.actor))

    for t in (await db.execute(select(TrainingSession).where(TrainingSession.customer_id == customer_id))).scalars():
        detail = " · ".join(x for x in (t.format and f"{t.format} · {t.delivered_by}", t.outcome, t.follow_up_text) if x)
        items.append(_item("training", t.session_date, f"Training: {t.topic_area}", detail or None,
                           flag="follow-up needed" if t.follow_up_needed else "resolved"))

    audit = (await db.execute(
        select(AuditLog).where(AuditLog.target_type == "customer", AuditLog.target_id == target)
    )).scalars().all()
    for a in audit:
        if a.action not in _AUDIT_NOISE:
            items.append(_item("system", a.created_at, a.action.replace("_", " ").replace(".", " · "), a.detail, actor=a.actor))
    if refs:
        case_audit = (await db.execute(
            select(AuditLog).where(AuditLog.target_type == "case", AuditLog.target_id.in_(refs),
                                   AuditLog.action.in_(list(_CASE_AUDIT_KIND)))
        )).scalars().all()
        for a in case_audit:
            what = a.action.split(".", 1)[1].replace("_", " ").capitalize()
            items.append(_item(_CASE_AUDIT_KIND[a.action], a.created_at,
                               f"{what} — {title_by_ref.get(a.target_id, a.target_id)}", a.detail,
                               ref=a.target_id, actor=a.actor))

    out = sorted((i for i in items if i), key=lambda i: i["when"], reverse=True)
    return out[:_MAX_ITEMS]
