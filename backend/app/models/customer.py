from datetime import date, datetime
from sqlalchemy import Integer, String, Boolean, Date, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)  # Premier / Strategic / Scale
    csm: Mapped[str] = mapped_column(String(100), nullable=False)
    arr_gbp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), default="Active")  # Active / Cancelled

    # Commercial
    product: Mapped[str | None] = mapped_column(String(100))
    plan: Mapped[str | None] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(100))
    timezone: Mapped[str | None] = mapped_column(String(50))
    contacts: Mapped[str | None] = mapped_column(Text)
    renewal_date: Mapped[date | None] = mapped_column(Date)
    seats: Mapped[int] = mapped_column(Integer, default=0)
    sla_tier: Mapped[str] = mapped_column(String(50), default="Standard")

    # Health & sentiment
    health_score: Mapped[int] = mapped_column(Integer, default=50)
    sentiment: Mapped[str] = mapped_column(String(30), default="Neutral")
    churn_risk: Mapped[str] = mapped_column(String(20), default="Medium")

    # Hypercare — a temporary heightened-attention window (e.g. post-migration
    # stabilization), manually set with a human-estimated end date. No
    # reliable Jira signal exists to detect this automatically (confirmed
    # live: the real `Hypercare_migration` label exists but only appears on
    # 5 tickets ever, is migration-specific, and carries no end date).
    hypercare_until: Mapped[date | None] = mapped_column(Date)
    hypercare_reason: Mapped[str | None] = mapped_column(String(200))

    # Real last-support-case date, refreshed weekly by
    # _customer_engagement_refresh() (scheduler.py) from live Jira — never
    # computed per-request (a full scan takes minutes). NULL means no real
    # case has ever been matched to this customer. Quiet/Dormant tiers
    # (6mo / 12mo) are derived from this at render time, not stored
    # separately, so the threshold can change without a migration.
    last_case_activity_at: Mapped[date | None] = mapped_column(Date)

    # The exact raw value ("Name|<id>") this customer's real Jira Customer
    # picklist (customfield_10047) option holds — discovered once via a
    # bounded recent-tickets scan (customer_case_stats()) and persisted
    # here so it never needs rediscovering. Confirmed live this mattered:
    # the scan only looks at the ~2000 most recently-updated project-wide
    # tickets, so a customer with no activity more recent than the rest of
    # a genuinely busy Jira instance's churn can silently fall out of that
    # window — a real customer (95 open tickets) intermittently returned
    # "not found" a few hours after its value was first discovered, purely
    # because other customers' tickets had since been updated more recently.
    jira_customer_field_value: Mapped[str | None] = mapped_column(String(200))

    # Upgrade tracking
    upgrades_used: Mapped[int] = mapped_column(Integer, default=0)
    upgrades_limit: Mapped[int] = mapped_column(Integer, default=10)
    prod_version: Mapped[str | None] = mapped_column(String(30))
    test_version: Mapped[str | None] = mapped_column(String(30))

    # After-hours upgrade allowance — tracking only (hours + note on the
    # Upgrade itself), never a computed charge. Not every package includes
    # this at all, distinct from the general upgrades_limit above.
    after_hours_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    after_hours_limit: Mapped[int] = mapped_column(Integer, default=0)
    after_hours_used: Mapped[int] = mapped_column(Integer, default=0)

    # Infrastructure
    infra: Mapped[str] = mapped_column(String(20), default="Old")  # Old / New / Mixed
    ip_fw: Mapped[bool] = mapped_column(Boolean, default=False)
    wildfly8: Mapped[bool] = mapped_column(Boolean, default=False)
    sso: Mapped[str] = mapped_column(String(50), default="None")
    integrations: Mapped[str] = mapped_column(String(200), default="None")
    api_customer: Mapped[bool] = mapped_column(Boolean, default=False)

    # Still on the old Java desktop client ("JVMS" in the validated VMS
    # customer list) rather than the modern web app — a real, distinct
    # population that has actively refused the web migration, confirmed
    # from the same validated source used for the Contacts/product-tag
    # correction pass. Deliberately just a flag, not a version field — the
    # source data didn't carry a reliable per-customer JVM version for
    # every row, and guessing one would be worse than not having it.
    jvm_client: Mapped[bool] = mapped_column(Boolean, default=False)

    # Scheduling preferences
    pref_days: Mapped[str | None] = mapped_column(String(100))
    notice_required: Mapped[str | None] = mapped_column(String(50))
    blackout_periods: Mapped[str | None] = mapped_column(String(200))

    # Cached AI-generated summary of reported issues (on-demand, not per-page-load)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_summary_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Manual, free-text — e.g. "don't use the default user, create one per
    # support engineer" / "add each engineer individually in Azure AD". No
    # API gives this; it's tribal knowledge that keeps getting re-learned.
    tenant_login_notes: Mapped[str | None] = mapped_column(Text)

    # Relationships
    cases: Mapped[list["Case"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    upgrades: Mapped[list["Upgrade"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    migration: Mapped["MigrationProject | None"] = relationship(back_populates="customer", uselist=False, cascade="all, delete-orphan")
    training_gaps: Mapped[list["TrainingGap"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    training_sessions: Mapped[list["TrainingSession"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    notes: Mapped[list["CustomerNote"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    sso_onboarding: Mapped["SSOOnboarding | None"] = relationship(back_populates="customer", uselist=False, cascade="all, delete-orphan")
    tenant_info: Mapped[list["CustomerTenantInfo"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    cancellation: Mapped["Cancellation | None"] = relationship(back_populates="customer", uselist=False, cascade="all, delete-orphan")


from app.models.case import Case  # noqa: E402
from app.models.upgrade import Upgrade  # noqa: E402
from app.models.migration_project import MigrationProject  # noqa: E402
from app.models.training import TrainingGap, TrainingSession  # noqa: E402
from app.models.note import CustomerNote  # noqa: E402
from app.models.sso_onboarding import SSOOnboarding  # noqa: E402
from app.models.customer_tenant_info import CustomerTenantInfo  # noqa: E402
from app.models.cancellation import Cancellation  # noqa: E402
