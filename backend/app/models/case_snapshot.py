from datetime import date, datetime
from sqlalchemy import Integer, Date, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class DailyCaseSnapshot(Base):
    __tablename__ = "daily_case_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # customer_id is NULL for the global (mine) row

    open_count: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    closed_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_snapshot_date_customer", "snapshot_date", "customer_id", unique=True),
    )
