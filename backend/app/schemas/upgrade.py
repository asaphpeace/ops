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
    request_type: str | None = None
    blocked: bool = False
    blocked_reason: str | None = None
    scheduled_at: datetime | None = None
    after_hours: bool = False
    after_hours_billed_hours: float | None = None
    after_hours_billing_note: str | None = None
    linked_vms_ref: str | None = None


class UpgradeUpdate(BaseModel):
    stage: str | None = None
    # Correctable after creation — same reasoning as Customer.prod_version's
    # own gap: some completed upgrades never got a real version recorded
    # (e.g. synced from a ticket with no parseable version, stored as
    # "Unknown") and there was previously no way to fix that except raw SQL.
    to_version: str | None = None
    blocked: bool | None = None
    blocked_reason: str | None = None
    scheduled_at: datetime | None = None
    duration_minutes: int | None = None
    confirmed_at: datetime | None = None
    devops_confirmed_at: datetime | None = None
    customer_confirmed_at: datetime | None = None
    devops_engineer: str | None = None
    verified_at: datetime | None = None
    date_done: datetime | None = None
    cancel_slot: bool | None = None
    # cancel_slot=True clears scheduled_at and cancels the calendar event.
    # Not a plain None-assignment because exclude_none=True can't express "clear this".
    after_hours: bool | None = None
    after_hours_billed_hours: float | None = None
    after_hours_billing_note: str | None = None


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
    request_type: str | None = None
    blocked: bool
    blocked_reason: str | None
    linked_vms_ref: str | None = None
    scheduled_at: datetime | None
    after_hours: bool = False
    after_hours_billed_hours: float | None = None
    after_hours_billing_note: str | None = None
    duration_minutes: int = 120
    google_event_id: str | None = None
    confirmed_at: datetime | None
    devops_confirmed_at: datetime | None = None
    customer_confirmed_at: datetime | None = None
    devops_engineer: str | None = None
    verified_at: datetime | None
    date_done: datetime | None
    created_at: datetime
    updated_at: datetime
    customer_name: str | None = None
    customer_tier: str | None = None
    # Not a DB column — computed by _enrich() against
    # CustomerTenantInfo.self_serviceable for this upgrade's
    # (customer_id, environment). True means the user can run this upgrade
    # themself, no DevOps engineer needed.
    is_self_service: bool = False
    # Real, live-synced CustomerTenantInfo.release for this customer+
    # environment right now — only ever populated on the Verified Done
    # history bucket (pipeline_summary()), deliberately kept separate from
    # to_version (this ticket's recorded target, which can be stale or
    # "Unknown" for a badly-parsed historical ticket).
    current_version: str | None = None
    current_version_synced_at: datetime | None = None

    model_config = {"from_attributes": True}
