from datetime import date, datetime
from sqlalchemy import Integer, String, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class TrainingGap(Base):
    __tablename__ = "training_gaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    area: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    source_case_ref: Mapped[str | None] = mapped_column(String(30))
    count: Mapped[int] = mapped_column(Integer, default=1)
    logged_at: Mapped[date] = mapped_column(Date, default=date.today)

    customer: Mapped["Customer"] = relationship(back_populates="training_gaps")


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    topic_area: Mapped[str] = mapped_column(String(100), nullable=False)
    format: Mapped[str | None] = mapped_column(String(100))
    delivered_by: Mapped[str] = mapped_column(String(50), default="Asaph")
    outcome: Mapped[str | None] = mapped_column(String(200))
    follow_up_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    follow_up_text: Mapped[str | None] = mapped_column(String(300))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    customer: Mapped["Customer"] = relationship(back_populates="training_sessions")


from app.models.customer import Customer  # noqa: E402
