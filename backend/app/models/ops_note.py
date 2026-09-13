from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class OpsNote(Base):
    """A manually-pasted chunk of real operational context — Slack
    discussion, a hallway conversation, anything relevant that lives
    outside Jira/this app. Confirmed no Slack API access is available (no
    workspace admin permission to install a bot app), so this is the
    paste-in equivalent of Case/VmsBug.rovo_context, but not tied to one
    specific ticket — a running log the Ollama supervisor
    (observation_signals.py) and the existing AI summaries (digest.py)
    can both draw real, human-known context from, unlike anything Jira
    itself would ever surface."""

    __tablename__ = "ops_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)

    # Free-text label for where this came from — "#support-ops", "DM with
    # Gisele" — not a structured channel id, since there's no Slack API to
    # validate one against.
    source_label: Mapped[str | None] = mapped_column(String(100))

    # Both optional, both how a note connects to real entities — a human
    # tags these by hand; no auto-parsing of the pasted text is attempted.
    customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("customers.id", ondelete="SET NULL"))
    jira_ref: Mapped[str | None] = mapped_column(String(30))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # NULL = not yet processed by services/knowledge_extraction.py. Notes
    # are create-only (no edit endpoint exists), so "already extracted" is a
    # simple one-way flag, not something that needs an updated_at/watermark
    # comparison to detect re-processing.
    knowledge_extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped["Customer | None"] = relationship()


from app.models.customer import Customer  # noqa: E402
