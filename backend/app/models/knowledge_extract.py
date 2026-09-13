from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class KnowledgeExtract(Base):
    """One categorized insight mined from a real OpsNote (pasted Slack
    context) by the local Ollama model — services/knowledge_extraction.py.

    Unlike the deterministic-first supervisor (observation_signals.py +
    ollama_supervisor.py), this IS a genuine discovery task: a raw Slack
    dump has no structured signal for Sedna Ops to pre-compute, so the
    model has to read and interpret free text itself. Mitigated the same
    way as everywhere else this matters in this app: JSON-mode output,
    a fixed, validated category vocabulary (anything else is dropped, never
    stored), and every row traces back to its real source_note_id so a
    human can check the original text an extract came from."""

    __tablename__ = "knowledge_extracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Trend | System | Process | Procedure | Challenge | Relationship —
    # exactly the taxonomy asked for, fixed and validated at parse time
    # (services/knowledge_extraction.py::_ALLOWED_CATEGORIES). "Relationship"
    # is free-text ("how X connects to Y"), not a graph — confirmed with
    # the user directly.
    category: Mapped[str] = mapped_column(String(20))

    summary: Mapped[str] = mapped_column(Text)

    source_note_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ops_notes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    model_used: Mapped[str] = mapped_column(String(50))

    # Lightweight quality control for a small local model doing genuine
    # extraction from unstructured text — hide a wrong/unhelpful entry from
    # the browse view without deleting the row (keeps it traceable/auditable).
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    source_note: Mapped["OpsNote"] = relationship()


from app.models.ops_note import OpsNote  # noqa: E402
