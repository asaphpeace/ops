from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class MigrationProject(Base):
    __tablename__ = "migration_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    stage: Mapped[str] = mapped_column(String(40), default="Not Started")
    # Not Started / Assessed / DevOps Priority / Cust. Contacted / Downtime Agreed / In Progress / Verifying / Complete

    assignee: Mapped[str | None] = mapped_column(String(50))
    complexity: Mapped[str] = mapped_column(String(20), default="Medium")  # Low / Medium / High / Very High
    ip_fw: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_upgrade: Mapped[bool] = mapped_column(Boolean, default=False)

    stalled: Mapped[bool] = mapped_column(Boolean, default=False)
    stalled_days: Mapped[int] = mapped_column(Integer, default=0)

    downtime_agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    downtime_duration_mins: Mapped[int] = mapped_column(Integer, default=240)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # NULL = a not-yet-actioned candidate (e.g. from a bulk import like
    # Elias's Old-AWS environment list) — surfaced only in the Migration
    # Priority backlog, never in the kanban. Set once a human clicks
    # "Initiate", which is what actually puts it in the "Not Started" kanban
    # column; ad-hoc migrations created via "+ Start Migration" are
    # initiated immediately, since a human explicitly chose to start them.
    initiated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ip_notes: Mapped[str | None] = mapped_column(Text)
    integration_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    customer: Mapped["Customer"] = relationship(back_populates="migration")


from app.models.customer import Customer  # noqa: E402
