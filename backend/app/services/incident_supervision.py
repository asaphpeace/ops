"""Deterministic supervision over the Incident/IncidentRemediation feature —
same "detect, never auto-act" pattern as services/upgrade_supervision.py.

stalled_incidents(): a real Open, product-source incident with no recorded
activity (a decision logged, a customer notified, or resolution) in
STALLED_DAYS — the "nothing forces re-engagement" gap found while
researching cybersecurity incident-response practice for Incident #4.
Staleness is measured by last REAL activity (via AuditLog), not just
detected_at age, so an incident someone is actively working on never
falsely flags just because it's been open a while."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.incident import Incident

STALLED_DAYS = 7

_ACTIVITY_ACTIONS = ("incident.decision_logged", "incident.customer_notified", "incident.resolved")


async def stalled_incidents(db: AsyncSession) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=STALLED_DAYS)

    incidents = (
        await db.execute(
            select(Incident).where(
                Incident.status == "Open",
                Incident.source == "product",
                Incident.phase.not_in(("Remediating Customers", "Closed")),
            )
        )
    ).scalars().all()
    if not incidents:
        return []

    ids = [str(i.id) for i in incidents]
    last_activity_result = await db.execute(
        select(AuditLog.target_id, AuditLog.created_at)
        .where(
            AuditLog.target_type == "incident",
            AuditLog.target_id.in_(ids),
            AuditLog.action.in_(_ACTIVITY_ACTIONS),
        )
        .order_by(AuditLog.created_at.desc())
    )
    last_activity_by_id: dict[str, datetime] = {}
    for target_id, created_at in last_activity_result.all():
        if target_id not in last_activity_by_id:
            last_activity_by_id[target_id] = created_at

    out = []
    for inc in incidents:
        last = last_activity_by_id.get(str(inc.id))
        anchor = last or inc.detected_at
        if anchor and anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)
        if anchor is None or anchor > cutoff:
            continue
        days_stale = (datetime.now(timezone.utc) - anchor).days if anchor else None
        out.append({
            "id": inc.id,
            "title": inc.title,
            "severity": inc.severity,
            "phase": inc.phase,
            "days_stale": days_stale,
        })
    return sorted(out, key=lambda d: d["days_stale"] or 0, reverse=True)
