from datetime import datetime
from pydantic import BaseModel


class CaseCreate(BaseModel):
    customer_id: int
    jira_ref: str
    title: str
    case_type: str
    environment: str = "PROD"
    status: str = "Active"
    priority: str = "Medium"
    sla_days: int | None = None
    days_open: int = 0
    defect_status: str | None = None
    root_cause: str | None = None
    blocked: bool = False
    blocked_reason: str | None = None
    linked_case_ref: str | None = None


class CaseUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    days_open: int | None = None
    defect_status: str | None = None
    root_cause: str | None = None
    blocked: bool | None = None
    blocked_reason: str | None = None
    linked_case_ref: str | None = None
    assigned_to: str | None = None
    resolution_note: str | None = None
    rovo_context: str | None = None
    needs_csm_briefing: bool | None = None
    escalate: bool | None = None
    # escalate=True stamps escalated_at=now(); escalate=False clears it.
    # Not a plain field because escalated_at is a timestamp, not a bool.
    lane_override: str | None = None
    # One of: me / devops / dev / customer / csm / escalated. Corrects the
    # mention-derived lane guess when it's wrong. Pass "" to clear it.


class CaseOut(BaseModel):
    id: int
    customer_id: int
    jira_ref: str
    title: str
    case_type: str
    environment: str
    status: str
    priority: str
    sla_days: int | None
    days_open: int
    defect_status: str | None
    root_cause: str | None
    blocked: bool
    blocked_reason: str | None
    linked_case_ref: str | None
    assigned_to: str | None = None
    resolution_note: str | None = None
    rovo_context: str | None = None
    rovo_context_at: datetime | None = None
    needs_csm_briefing: bool = False
    comment_count: int = 0
    escalated_at: datetime | None = None
    status_changed_at: datetime | None = None
    last_mention_name: str | None = None
    last_mention_at: datetime | None = None
    lane_override: str | None = None
    first_public_reply_at: datetime | None = None
    ttfr_hours: float | None = None
    ttfr_breached: bool | None = None
    jira_customer_name: str | None = None
    linked_vms_ref: str | None = None
    linked_vms_refs: str | None = None
    related_case_refs: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    customer_name: str | None = None
    customer_tier: str | None = None

    model_config = {"from_attributes": True}


class CaseTimelineEntry(BaseModel):
    action: str
    detail: str | None
    actor: str
    created_at: datetime


class RelatedCaseSummary(BaseModel):
    jira_ref: str
    title: str | None = None
    customer_name: str | None = None
    status: str | None = None


class CaseDetailOut(CaseOut):
    timeline: list[CaseTimelineEntry] = []
    related_cases: list[RelatedCaseSummary] = []
