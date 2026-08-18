from datetime import datetime
from pydantic import BaseModel


class UpgradeCreate(BaseModel):
    customer_id: int
    jira_ref: str | None = None
    environment: str
    from_version: str | None = None
    to_version: str
    upgrade_type: str = "Small"
    stage: str = "Requested"
    source: str = "Customer request"
    blocked: bool = False
    blocked_reason: str | None = None
    scheduled_at: datetime | None = None


class UpgradeUpdate(BaseModel):
    stage: str | None = None
    blocked: bool | None = None
    blocked_reason: str | None = None
    scheduled_at: datetime | None = None
    confirmed_at: datetime | None = None
    verified_at: datetime | None = None
    date_done: datetime | None = None


class UpgradeOut(BaseModel):
    id: int
    customer_id: int
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
    confirmed_at: datetime | None
    verified_at: datetime | None
    date_done: datetime | None
    created_at: datetime
    updated_at: datetime
    customer_name: str | None = None
    customer_tier: str | None = None

    model_config = {"from_attributes": True}
