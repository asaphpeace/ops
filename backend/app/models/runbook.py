from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Runbook(Base):
    """Real, human-authored operational procedures (e.g. 'restart auth-api
    on a single-VM tenant without dropping sessions'). Starts empty — no
    fabricated procedure text is ever seeded; DevOps/engineering populates
    these over time via the Infrastructure tab. Matched to a customer at
    render time by simple field checks (hosting model / engine substring),
    not a rules DSL."""
    __tablename__ = "runbooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(300))

    # Trigger condition — both nullable; null means "always relevant".
    trigger_hosting_model: Mapped[str | None] = mapped_column(String(30))
    trigger_engine_contains: Mapped[str | None] = mapped_column(String(50))

    body: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
