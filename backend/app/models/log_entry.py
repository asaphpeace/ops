from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Text, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class LogEntry(Base):
    """
    A real, imported AWS log line/event — a deliberately scoped substitute
    for a real log platform (Humio/Falcon LogScale), not a replica: no
    live ingest pipeline, no query language, no live tail. Same manual
    "export -> paste -> ingest" pattern as AwsResource, honest about the
    tradeoff: this handles a bounded, periodically-imported time window
    per log group, not continuous high-volume streaming.

    Four real AWS log shapes are unified onto one row shape here:
      - "application" / "rds" / "vpc_flow" — all delivered through
        CloudWatch Logs (`aws logs filter-log-events`), same real event
        shape ({timestamp, message, logStreamName}) regardless of what's
        actually logging to that log group.
      - "cloudtrail" — structurally different (`aws cloudtrail
        lookup-events`), a real JSON event, not a freeform text line.
    `message` is always a real, searchable single line (the raw
    CloudWatch message for the first three; a synthesized one-line
    summary — "{EventName} by {user} from {ip}" — for CloudTrail, since a
    full-text search still needs one line to search). `raw_json` keeps
    the full original record for anyone who wants the exact fields.

    Full-text search is Postgres tsvector on `message` — the same
    precedent already proven in this codebase for OllamaSearchIndex, at a
    real, comparable data volume (a periodic bounded import, not a real
    log platform's continuous terabyte-scale ingest).
    """

    __tablename__ = "log_entries"
    __table_args__ = (
        UniqueConstraint("log_type", "source_group", "event_id", name="uq_log_entry_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # "application" | "rds" | "cloudtrail" | "vpc_flow"
    log_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # The real CloudWatch Log Group name (or a human label for CloudTrail
    # region/trail) — set by the human at import time, same as
    # AwsResource.aws_environment.
    source_group: Mapped[str] = mapped_column(String(200), nullable=False)
    # eventId (CloudWatch) / EventId (CloudTrail) — the real per-record
    # identifier AWS assigns, used for the unique constraint above so a
    # re-import of an overlapping time window doesn't duplicate rows.
    event_id: Mapped[str] = mapped_column(String(80), nullable=False)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str | None] = mapped_column(String(20))  # ERROR/WARN/INFO — best-effort, application logs only

    raw_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Optional link to the real AWS resource this log group belongs to —
    # per the confirmed decision, logs should show up in context on a
    # resource/customer's own view, not as a disconnected page.
    aws_resource_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("aws_resources.id", ondelete="SET NULL"), index=True
    )

    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    resource: Mapped["AwsResource | None"] = relationship()


from app.models.aws_resource import AwsResource  # noqa: E402
