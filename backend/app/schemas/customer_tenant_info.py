from datetime import datetime
from pydantic import BaseModel


class TenantInfoCreate(BaseModel):
    environment: str  # PROD / TEST / DEV
    subdomain: str


class TenantInfoOut(BaseModel):
    id: int
    customer_id: int
    environment: str
    subdomain: str
    self_serviceable: bool = False
    release: str | None = None
    reported_environment: str | None = None
    is_azure_installation: bool | None = None
    is_auth0_installation: bool | None = None
    is_jvms_mode: bool | None = None
    is_pure_web: bool | None = None
    last_synced_at: datetime | None = None
    last_sync_error: str | None = None
    cert_expires_at: datetime | None = None
    cert_issuer: str | None = None
    cert_checked_at: datetime | None = None
    cert_check_error: str | None = None
    created_at: datetime
    updated_at: datetime
    # Not a DB column — set transiently on the ORM row by sync_tenant_info()
    # when a PROD sync's newly-detected version matches an open product
    # incident's fix threshold, so the frontend can toast it immediately.
    matched_incidents: list[dict] = []

    model_config = {"from_attributes": True}
