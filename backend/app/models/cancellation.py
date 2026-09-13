from datetime import date, datetime
from sqlalchemy import Integer, String, Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Cancellation(Base):
    __tablename__ = "cancellations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )

    # Stage: Requested -> DevOps Notified -> Decommissioned. Always starts at
    # Requested — the customer's email to CS is treated as final, there is
    # no retention/save-attempt stage modeled here.
    stage: Mapped[str] = mapped_column(String(30), default="Requested")

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    reason: Mapped[str | None] = mapped_column(Text)

    # Optional — CS can attach a real Jira ticket if one was created for the
    # cancellation, but most never carry a durable component/label to key
    # off (confirmed live against real Jira), so this is never auto-derived.
    jira_ref: Mapped[str | None] = mapped_column(String(20))

    # Due at the end of the customer's yearly subscription — pre-filled
    # from Customer.renewal_date when set, otherwise entered manually
    # (most customers have no renewal_date on file today).
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)

    devops_contact: Mapped[str | None] = mapped_column(String(150))
    devops_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decommissioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    customer: Mapped["Customer"] = relationship(back_populates="cancellation")


from app.models.customer import Customer  # noqa: E402
