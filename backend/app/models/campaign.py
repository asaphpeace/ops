from datetime import datetime
from sqlalchemy import Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)

    # Set when this campaign exists to notify a product incident's affected
    # customers — real notification tracking, not a bare toggle (see
    # IncidentRemediation). SET NULL so a campaign survives if the incident
    # record is ever removed.
    incident_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("incidents.id", ondelete="SET NULL"))

    # Comma-joined customer ids — same convention as Case.linked_vms_refs/
    # related_case_refs (no join table): campaigns are created every 2-3
    # months, a handful of rows ever, so there's no performance reason to
    # normalize this into a real many-to-many table. A real segment can
    # cover most of the customer base, so this is Text, not a short varchar.
    customer_ids: Mapped[str] = mapped_column(Text)

    # Draft -> Sent. "Sent" is a manual confirmation, not a real send event —
    # this app has no outbound-communication capability (confirmed this
    # session); the actual message goes out through the user's own email
    # client. sent_at just records when that manual step happened.
    status: Mapped[str] = mapped_column(String(20), default="Draft")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
