from datetime import datetime
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class UnmatchedUpgradeCustomer(Base):
    """A distinct customer-name string seen on real Jira upgrade tickets
    (component 'PROD Upgrade'/'TEST / DEV Upgrade') that didn't match any
    local Customer, by exact name or suffix-stripped normalization. One row
    per distinct name, not per ticket — a real company can have many
    upgrade tickets under the same unresolved name."""

    __tablename__ = "unmatched_upgrade_customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    ticket_count: Mapped[int] = mapped_column(Integer, default=0)
    sample_jira_refs: Mapped[str] = mapped_column(String(500), default="")
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
