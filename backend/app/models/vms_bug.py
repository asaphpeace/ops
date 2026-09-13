from datetime import datetime
from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class VmsBug(Base):
    """
    A real VMS-project issue (Bug/Task/Story — never a Sub-task, confirmed
    against live data) linked from one or more DSD support cases via Jira
    issuelinks. One row per distinct bug, not duplicated per linking case.
    """

    __tablename__ = "vms_bugs"

    jira_ref: Mapped[str] = mapped_column(String(30), primary_key=True)
    issue_type: Mapped[str] = mapped_column(String(50), default="")
    status: Mapped[str] = mapped_column(String(50), default="")
    fix_version: Mapped[str | None] = mapped_column(String(50))
    labels: Mapped[str] = mapped_column(String(500), default="")

    # Real Jira Software sprint (customfield_10010) and assignee — the actual
    # "dev queue, prioritized, assigned to a dev for a sprint" data, synced
    # from Jira rather than reinvented as a local board.
    sprint_name: Mapped[str | None] = mapped_column(String(100))
    sprint_state: Mapped[str | None] = mapped_column(String(20))
    assignee: Mapped[str | None] = mapped_column(String(200))

    ai_summary: Mapped[str | None] = mapped_column(String(2000))
    ai_summary_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Free-text context pasted in manually (e.g. from asking Rovo Chat in the
    # Jira UI) — same reasoning as Case.rovo_context: exploratory/supplementary,
    # folded into summarize_bug_impact()'s local context for free, independent
    # of whether live Rovo credentials are configured.
    rovo_context: Mapped[str | None] = mapped_column(Text)
    rovo_context_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Real Jira created/resolutiondate — not fetched before this was added,
    # so historical dates only appear once each bug is re-synced (Jira's own
    # field always existed; this backfills real dates immediately on next
    # sync, unlike the AuditLog timeline which is genuinely forward-only).
    jira_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    jira_resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
