from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Upgrade(Base):
    __tablename__ = "upgrades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)

    jira_ref: Mapped[str | None] = mapped_column(String(30), index=True)
    environment: Mapped[str] = mapped_column(String(10), nullable=False)  # PROD / TEST / DEV
    from_version: Mapped[str | None] = mapped_column(String(30))
    to_version: Mapped[str] = mapped_column(String(30), nullable=False)
    upgrade_type: Mapped[str] = mapped_column(String(20), default="Small")  # Small / Complex / Maintenance

    # Pipeline stage
    stage: Mapped[str] = mapped_column(String(40), default="Requested")
    # Requested / DevOps Approval / Cust. Confirmed / Scheduled / In Progress / Verified Done

    source: Mapped[str] = mapped_column(String(100), default="Customer request")

    # The originating ticket's real Jira Request Type at creation time (e.g.
    # "Upgrade or Installation Request"), captured once and never refreshed.
    # This is the ONLY reliable way to tell a genuine sys-admin upgrade
    # request apart from a Pending-Upgrade-status ticket that also routes
    # through _ensure_upgrade_from_ticket() — both produce an identical
    # Upgrade row otherwise, and neither ever gets a local Case row (Case
    # creation is deliberately skipped for Upgrade-classified tickets), so
    # cross-referencing a Case's request_type (the original approach) can
    # never work for these. Null for manually-created rows and anything
    # created before this column existed.
    request_type: Mapped[str | None] = mapped_column(String(100))

    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_reason: Mapped[str | None] = mapped_column(String(500))

    # Set when source="Bug/Incident fix" and a real VMS bug is known — lets
    # the overdue bug-fix-upgrade supervision logic (My Desk Flags row,
    # Release Intelligence) find and cross-reference these, since they sit
    # outside the normal sys-admin-queue workflow and can otherwise go
    # unnoticed. Optional even for that source — sometimes only the ask is
    # known, not a tracked VmsBug ref.
    linked_vms_ref: Mapped[str | None] = mapped_column(String(30))

    # After-hours tracking only — no computed charge, no invoicing
    # integration. Hours/note are typically only known once the work is
    # actually done, not at scheduling time.
    after_hours: Mapped[bool] = mapped_column(Boolean, default=False)
    after_hours_billed_hours: Mapped[float | None] = mapped_column(Float)
    after_hours_billing_note: Mapped[str | None] = mapped_column(String(500))

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Real, distinct confirmation from each party — confirmed_at above is a
    # dead field (nothing in the live write path ever sets it, only
    # seed.py's fixtures) and was never two-party anyway. These two are the
    # actual fix for a real incident: an upgrade got scheduled and completed
    # without either DevOps or the customer ever formally confirming the
    # slot, and nothing in the app noticed. See
    # services/upgrade_supervision.py::unconfirmed_upgrades().
    devops_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Which real DevOps engineer (Martin Fure / Elias Hjellestad — the same
    # DEVOPS_ROSTER already used for lane classification) is responsible for
    # this upgrade — separate from devops_confirmed_at, which only tracks
    # whether a slot was confirmed, not by whom. Null for self-serviceable
    # upgrades (see CustomerTenantInfo.self_serviceable) and manual entries
    # where it isn't yet known.
    devops_engineer: Mapped[str | None] = mapped_column(String(100))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_done: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Google Calendar — internal-only booking, one-way push (Command Centre)
    google_event_id: Mapped[str | None] = mapped_column(String(200))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=120)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    customer: Mapped["Customer"] = relationship(back_populates="upgrades")


from app.models.customer import Customer  # noqa: E402
