from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class JiraUnmatched(Base):
    """Jira issues seen during polling that have no matching local customer/case."""

    __tablename__ = "jira_unmatched"

    jira_ref: Mapped[str] = mapped_column(String(30), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    issue_type: Mapped[str] = mapped_column(String(50), default="")
    case_type: Mapped[str] = mapped_column(String(30), default="Support")
    priority: Mapped[str] = mapped_column(String(10), default="Medium")
    labels: Mapped[str] = mapped_column(String(500), default="")
    days_open: Mapped[int] = mapped_column(Integer, default=0)
    jira_customer_name: Mapped[str | None] = mapped_column(String(200))
    # Jira Service Desk "Request Type" (customfield_10014) — e.g. "Upgrade or
    # Installation Request". Distinct from status/label/component; captured
    # so case_type classification doesn't rely solely on status.
    request_type: Mapped[str | None] = mapped_column(String(100))
    # A human decided this ref isn't worth tracking as a Case — the poll's
    # auto-bridge (see poll_and_upsert()) must never resurrect it, even once
    # its customer name becomes resolvable. Mirrors UnmatchedUpgradeCustomer.dismissed.
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
