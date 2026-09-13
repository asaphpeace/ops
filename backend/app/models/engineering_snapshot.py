from datetime import date, datetime
from sqlalchemy import Integer, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class EngineeringDailySnapshot(Base):
    """One row per day — the Overview 'Estate posture' KPI history, so a
    delta ("+4 vs 30 days ago") has something real to diff against instead
    of being fabricated. Mirrors DailyCaseSnapshot's exact shape/precedent."""
    __tablename__ = "engineering_daily_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)

    estate_count: Mapped[int] = mapped_column(Integer, default=0)
    on_current_release_count: Mapped[int] = mapped_column(Integer, default=0)
    customer_exposure_count: Mapped[int] = mapped_column(Integer, default=0)
    legacy_footprint_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
