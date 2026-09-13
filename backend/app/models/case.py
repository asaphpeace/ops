from datetime import date, datetime
from sqlalchemy import Integer, String, Boolean, Date, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)

    jira_ref: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    case_type: Mapped[str] = mapped_column(String(30), nullable=False)  # Upgrade / Defect / Support / Training Gap
    environment: Mapped[str] = mapped_column(String(10), default="PROD")  # PROD / TEST / DEV
    status: Mapped[str] = mapped_column(String(50), default="Active")
    # Active / Awaiting Dev / Awaiting Customer / Awaiting DevOps / Requested / Closed

    # The real, uncollapsed Jira status string (e.g. "Waiting for support",
    # "Pending Upgrade") — status above is a deliberate 4-value simplification
    # of this for the rest of the app; raw_status exists so Case Mix by Status
    # can show the actual workflow stage, not the collapsed bucket.
    raw_status: Mapped[str | None] = mapped_column(String(60))

    priority: Mapped[str] = mapped_column(String(10), default="Medium")  # High / Medium / Low
    sla_days: Mapped[int | None] = mapped_column(Integer)
    sla_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    days_open: Mapped[int] = mapped_column(Integer, default=0)

    defect_status: Mapped[str | None] = mapped_column(String(200))
    root_cause: Mapped[str | None] = mapped_column(String(200))

    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_reason: Mapped[str | None] = mapped_column(String(500))
    blocked_by: Mapped[str | None] = mapped_column(String(50))
    linked_case_ref: Mapped[str | None] = mapped_column(String(30))

    assigned_to: Mapped[str | None] = mapped_column(String(200))
    follow_up_due: Mapped[date | None] = mapped_column(Date)
    resolution_note: Mapped[str | None] = mapped_column(Text)

    # Free-text context pasted in manually (e.g. from asking Rovo Chat in the
    # Jira UI) — deliberately separate from resolution_note, which means "what
    # actually fixed this" and is a distinct, still-unbuilt feature. This field
    # is exploratory/supplementary and can apply to an unresolved case. Folded
    # into summarize_customer_issues()'s local context in services/digest.py —
    # free, since it never triggers a live Rovo API call itself.
    rovo_context: Mapped[str | None] = mapped_column(Text)
    rovo_context_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    needs_csm_briefing: Mapped[bool] = mapped_column(Boolean, default=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)

    # Derived from the most recent non-bot internal (jsdPublic=False) Jira comment
    # that @mentions someone — the real handoff signal, since status/assignee don't move.
    last_mention_name: Mapped[str | None] = mapped_column(String(200))
    last_mention_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Manual correction when the mention-derived guess is wrong. One of:
    # me / devops / dev / customer / csm / escalated
    lane_override: Mapped[str | None] = mapped_column(String(20))

    first_public_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Native Jira "Initial Response" SLA cycle — authoritative TTFR when present
    # (confirmed live: populated on 100/100 sampled tickets, completed on 74/100).
    ttfr_hours: Mapped[float | None] = mapped_column(Float)
    ttfr_breached: Mapped[bool | None] = mapped_column(Boolean)

    # Real Jira "Customer" picklist value (customfield_10047), suffix id stripped —
    # the actual reporting organization, used to match/group tickets by customer.
    jira_customer_name: Mapped[str | None] = mapped_column(String(200))

    # Jira Service Desk "Request Type" (customfield_10014) — e.g. "Upgrade or
    # Installation Request". Lets case_type classification recognize a
    # sys-admin/upgrade ticket from creation, not just once status reaches
    # "Pending Upgrade".
    request_type: Mapped[str | None] = mapped_column(String(100))

    # Real linked VMS-project bug/task (via Jira issuelinks), when the DSD ticket
    # has escalated to development. See models/vms_bug.py.
    linked_vms_ref: Mapped[str | None] = mapped_column(String(30))

    # All real linked VMS bugs (comma-joined) when a ticket links more than one —
    # confirmed live (DSD-28129 links both VMS-19447 and VMS-22680). linked_vms_ref
    # stays untouched for backward compat; this is additive.
    linked_vms_refs: Mapped[str | None] = mapped_column(String(300))

    # Real DSD-to-DSD "Relates" issuelinks (comma-joined) — a signal that
    # multiple customers hit the same underlying issue, confirmed live
    # (DSD-30697 relates to 6 other DSD tickets) but previously discarded
    # entirely by _extract_vms_links()'s VMS-only key filter. NOT the same
    # as the dead, never-populated linked_case_ref field above.
    related_case_refs: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped["Customer"] = relationship(back_populates="cases")


from app.models.customer import Customer  # noqa: E402
