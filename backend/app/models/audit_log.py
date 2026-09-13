from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)  # user email or "system"
    action: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "case.status_updated"
    target_type: Mapped[str | None] = mapped_column(String(50))       # "case", "upgrade", "alert"
    target_id: Mapped[str | None] = mapped_column(String(100))        # case id, jira_ref, alert key
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_audit_log_action_target_ts", "action", "target_id", "created_at"),
    )
