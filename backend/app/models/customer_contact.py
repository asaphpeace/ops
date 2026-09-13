from datetime import datetime
from sqlalchemy import Boolean, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class CustomerContact(Base):
    __tablename__ = "customer_contacts"
    __table_args__ = (UniqueConstraint("customer_id", "email", name="uq_customer_contact_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    # How this contact was captured — "jira_confluence_search" for the
    # initial validated batch, "manual" for anything added later via the UI.
    source: Mapped[str] = mapped_column(String(50), default="manual")
    # Exactly one contact per customer is designated the main/technical
    # contact for outbound comms (Customer Comms only sends here instead of
    # the full stored list). Picked from real Jira ticket-reporter frequency
    # + recency where a match exists, otherwise a personal-vs-role-inbox
    # heuristic — see primary_contact_reason for which path was used.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    primary_contact_reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    customer: Mapped["Customer"] = relationship()


from app.models.customer import Customer  # noqa: E402
