from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)

    jira_ref: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    case_type: Mapped[str] = mapped_column(String(30), nullable=False)  # Upgrade / Defect / Support / Training Gap
    environment: Mapped[str] = mapped_column(String(10), default="PROD")  # PROD / TEST / DEV
    status: Mapped[str] = mapped_column(String(50), default="Active")
    # Active / Awaiting Dev / Awaiting Customer / Awaiting DevOps / Requested / Closed

    priority: Mapped[str] = mapped_column(String(10), default="Medium")  # High / Medium / Low
    sla_days: Mapped[int | None] = mapped_column(Integer)
    sla_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    days_open: Mapped[int] = mapped_column(Integer, default=0)

    defect_status: Mapped[str | None] = mapped_column(String(200))
    root_cause: Mapped[str | None] = mapped_column(String(200))

    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_reason: Mapped[str | None] = mapped_column(String(500))
    linked_case_ref: Mapped[str | None] = mapped_column(String(30))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    customer: Mapped["Customer"] = relationship(back_populates="cases")


from app.models.customer import Customer  # noqa: E402
