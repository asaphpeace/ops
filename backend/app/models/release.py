from datetime import date, datetime
from sqlalchemy import Integer, String, Boolean, Date, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Release(Base):
    __tablename__ = "releases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)
    released_at: Mapped[date] = mapped_column(Date, nullable=False)
    defects_fixed: Mapped[int] = mapped_column(Integer, default=0)
    improvements: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
