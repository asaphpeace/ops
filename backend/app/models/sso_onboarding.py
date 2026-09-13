from datetime import date, datetime
from sqlalchemy import Integer, String, Boolean, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class SSOOnboarding(Base):
    __tablename__ = "sso_onboarding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )

    # Which environments are in scope
    has_prod: Mapped[bool] = mapped_column(Boolean, default=True)
    has_test: Mapped[bool] = mapped_column(Boolean, default=False)

    # Stage: Not Started | Email Sent | Awaiting Reply | DevOps Configuring | SSO Live
    stage: Mapped[str] = mapped_column(String(30), default="Not Started")

    # IT contact at customer side
    it_contact_name: Mapped[str | None] = mapped_column(String(150))
    it_contact_email: Mapped[str | None] = mapped_column(String(200))

    # Step 1 — setup email
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    guest_invite_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    # Step 2 — customer reply fields
    reply_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    field_domain: Mapped[str | None] = mapped_column(String(200))
    field_client_id: Mapped[str | None] = mapped_column(String(200))
    field_secret: Mapped[str | None] = mapped_column(String(200))
    field_reply_url: Mapped[str | None] = mapped_column(String(500))
    field_app_id_uri: Mapped[str | None] = mapped_column(String(500))

    # Step 3/4 — devops + switchover
    devops_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    switchover_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    switchover_duration_mins: Mapped[int | None] = mapped_column(Integer)

    follow_up_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    # Originating DSD ticket when this row was auto-started from a real
    # customer request (title-keyword match — no authoritative Jira Request
    # Type exists for SSO the way "Upgrade or Installation Request" does for
    # upgrades). Null for manually-created records.
    source_jira_ref: Mapped[str | None] = mapped_column(String(30))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    customer: Mapped["Customer"] = relationship(back_populates="sso_onboarding")


from app.models.customer import Customer  # noqa: E402
