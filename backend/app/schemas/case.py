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
    created_at: datetime
    updated_at: datetime
    customer_name: str | None = None
    customer_tier: str | None = None

    model_config = {"from_attributes": True}
