from datetime import date, datetime
from sqlalchemy import Integer, String, Date, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class WeeklyReport(Base):
    """One row per ISO week — a stored SNAPSHOT of the fully-computed weekly
    ops report (Support/Bug/Upgrade/Migration/Incident impact + customers
    affected), not a live view. Storing the computed content, not just
    metadata, is deliberate: this report is presented in a real weekly
    DevOps priority meeting and exported as a PDF — it must read the same
    way if reopened later even though the underlying Jira/DB data keeps
    moving, and week-over-week trend deltas need a stable prior value to
    diff against, not a re-query that could drift. Mirrors the existing
    Draft/Sent precedent on Campaign (see models/campaign.py) and the
    persisted-computed-fact precedent on DailyCaseSnapshot/AiObservation."""
    __tablename__ = "weekly_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # ISO week label, e.g. "2026-W37" — the natural human/URL identifier for
    # a weekly report; unique so generate is idempotent per week.
    week: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    # Draft -> Published, mirrors Campaign's Draft/Sent exactly — content
    # stays editable/regeneratable while Draft, immutable once Published
    # (matches Campaign's own "content becomes fixed once Sent" rule).
    status: Mapped[str] = mapped_column(String(20), default="Draft", nullable=False)
    # The full computed report payload at generation time (every section in
    # the plan) — deliberately schemaless JSON rather than a dozen new
    # columns, since this is a read-mostly archival snapshot, not a table
    # queried by its internal fields.
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
