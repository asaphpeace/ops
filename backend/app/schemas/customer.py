from datetime import date, datetime
from pydantic import BaseModel


class CaseOut(BaseModel):
    id: int
    jira_ref: str
    title: str
    case_type: str
    environment: str
    status: str
    priority: str
    days_open: int
    defect_status: str | None
    root_cause: str | None
    blocked: bool
    blocked_reason: str | None
    linked_case_ref: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UpgradeOut(BaseModel):
    id: int
    jira_ref: str | None
    environment: str
    from_version: str | None
    to_version: str
    upgrade_type: str
    stage: str
    source: str
    blocked: bool
    blocked_reason: str | None
    scheduled_at: datetime | None
    verified_at: datetime | None
    date_done: datetime | None

    model_config = {"from_attributes": True}


class MigrationOut(BaseModel):
    id: int
    stage: str
    assignee: str | None
    complexity: str
    ip_fw: bool
    requires_upgrade: bool
    stalled: bool
    stalled_days: int
    downtime_agreed_at: datetime | None
    completed_at: datetime | None
    ip_notes: str | None
    integration_notes: str | None

    model_config = {"from_attributes": True}


class TrainingGapOut(BaseModel):
    id: int
    area: str
    description: str | None
    source_case_ref: str | None
    count: int
    logged_at: date

    model_config = {"from_attributes": True}


class TrainingSessionOut(BaseModel):
    id: int
    session_date: date
    topic_area: str
    format: str | None
    delivered_by: str
    outcome: str | None
    follow_up_needed: bool
    follow_up_text: str | None

    model_config = {"from_attributes": True}


class NoteOut(BaseModel):
    id: int
    text: str
    author: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomerOut(BaseModel):
    id: int
    name: str
    tier: str
    csm: str
    arr_gbp: int
    product: str | None
    plan: str | None
    region: str | None
    timezone: str | None
    contacts: str | None
    renewal_date: date | None
    seats: int
    sla_tier: str
    health_score: int
    sentiment: str
    churn_risk: str
    upgrades_used: int
    upgrades_limit: int
    prod_version: str | None
    test_version: str | None
    infra: str
    ip_fw: bool
    wildfly8: bool
    sso: str
    integrations: str
    api_customer: bool
    pref_days: str | None
    notice_required: str | None
    blackout_periods: str | None

    model_config = {"from_attributes": True}


class CustomerDetail(CustomerOut):
    cases: list[CaseOut] = []
    upgrades: list[UpgradeOut] = []
    migration: MigrationOut | None = None
    training_gaps: list[TrainingGapOut] = []
    training_sessions: list[TrainingSessionOut] = []
    notes: list[NoteOut] = []


class CustomerCreate(BaseModel):
    name: str
    tier: str
    csm: str
    arr_gbp: int = 0
    product: str | None = None
    plan: str | None = None
    region: str | None = None
    timezone: str | None = None
    contacts: str | None = None
    renewal_date: date | None = None
    seats: int = 0
    sla_tier: str = "Standard"
    health_score: int = 50
    sentiment: str = "Neutral"
    churn_risk: str = "Medium"
    upgrades_used: int = 0
    upgrades_limit: int = 10
    prod_version: str | None = None
    test_version: str | None = None
    infra: str = "Old"
    ip_fw: bool = False
    wildfly8: bool = False
    sso: str = "None"
    integrations: str = "None"
    api_customer: bool = False
    pref_days: str | None = None
    notice_required: str | None = None
    blackout_periods: str | None = None


class CustomerUpdate(CustomerCreate):
    pass
