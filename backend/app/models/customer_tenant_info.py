from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class CustomerTenantInfo(Base):
    """
    One row per (customer, environment) — a customer's PROD and TEST tenants
    can run different releases (confirmed live: gb-prod on 8.23.4, gb-test on
    8.27.0), so this can't be flattened onto Customer itself.

    `subdomain` is always manually entered — Dataloy tenant subdomains don't
    follow one consistent naming rule (some are a bare tenant code for prod
    with no suffix, e.g. "sfl"; others use an explicit "-prod"/"-test" suffix,
    e.g. "gb-prod"/"gb-test") so there's nothing to derive it from.
    """

    __tablename__ = "customer_tenant_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(10), nullable=False)  # PROD / TEST / DEV
    subdomain: Mapped[str] = mapped_column(String(100), nullable=False)

    # Real fact, confirmed live per (customer, environment): the user can
    # personally run the upgrade against this tenant via their own internal
    # environment tool, without DevOps at all. Backfilled from a real
    # cross-reference against that tool's environment list — see the
    # migration this column was added in for the confirmed pairs and how
    # they were verified (including a caught false-positive: a naive
    # substring match once matched "peak-test" to "Seapeak" instead of
    # "Peak People AS").
    self_serviceable: Mapped[bool] = mapped_column(Boolean, default=False)

    release: Mapped[str | None] = mapped_column(String(30))
    reported_environment: Mapped[str | None] = mapped_column(String(20))
    is_azure_installation: Mapped[bool | None] = mapped_column(Boolean)
    is_auth0_installation: Mapped[bool | None] = mapped_column(Boolean)
    is_jvms_mode: Mapped[bool | None] = mapped_column(Boolean)
    is_pure_web: Mapped[bool | None] = mapped_column(Boolean)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_error: Mapped[str | None] = mapped_column(String(500))

    # SSL cert probe result — same shape as last_synced_at/last_sync_error
    # above, deliberately: a bare TLS handshake on :443 against this same
    # subdomain, independent of the /info sync above (a tenant whose /info
    # sync fails can still have a perfectly readable, valid certificate).
    # Expiry status (valid/expiring/critical/expired) is derived at query
    # time from cert_expires_at, never stored, so it can't go stale between
    # scans — see services/cert_scan.py.
    cert_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cert_issuer: Mapped[str | None] = mapped_column(String(300))
    cert_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cert_check_error: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    customer: Mapped["Customer"] = relationship(back_populates="tenant_info")

    __table_args__ = (UniqueConstraint("customer_id", "environment", name="uq_customer_tenant_env"),)


from app.models.customer import Customer  # noqa: E402
