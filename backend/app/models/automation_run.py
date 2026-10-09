from datetime import datetime
from sqlalchemy import Integer, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AutomationRun(Base):
    """One job executed through the host runner (runner/sedna_runner.py) —
    today only aws-util's upgrade_environment.sh (dry-run or real) and its
    ECR tag check. The runner keeps jobs in memory only; this row is the
    durable record: who/what/when, the full log, and the post-check result.

    A real upgrade is only allowed after a successful dry-run of the same
    environment + version (dry_run_of_id points at it), so the app's own
    preview-then-confirm replaces the script's interactive prompt."""
    __tablename__ = "automation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))  # upgrade_environment / ecr_tag_check
    environment: Mapped[str | None] = mapped_column(String(100))
    from_version: Mapped[str | None] = mapped_column(String(40))
    target_version: Mapped[str | None] = mapped_column(String(40))
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)
    dry_run_of_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("automation_runs.id", ondelete="SET NULL"))
    customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("customers.id", ondelete="SET NULL"))

    status: Mapped[str] = mapped_column(String(20), default="running")  # running/succeeded/warning/failed/cancelled/lost
    runner_job_id: Mapped[str | None] = mapped_column(String(40))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    log: Mapped[str] = mapped_column(Text, default="")
    log_line_count: Mapped[int] = mapped_column(Integer, default=0)

    # Post-check: what the tenant's /info reported after the run.
    post_check_release: Mapped[str | None] = mapped_column(String(40))
    post_check_ok: Mapped[bool | None] = mapped_column(Boolean)
    post_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    actor: Mapped[str] = mapped_column(String(200), default="you")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped["Customer"] = relationship()
