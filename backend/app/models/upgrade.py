from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey
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
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_reason: Mapped[str | None] = mapped_column(String(500))

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_done: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    customer: Mapped["Customer"] = relationship(back_populates="upgrades")


from app.models.customer import Customer  # noqa: E402
