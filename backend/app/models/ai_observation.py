from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AiObservation(Base):
    """Advisory-only findings from the local Ollama supervisor
    (services/ollama_supervisor.py). Never written to by anything that also
    mutates Case/Upgrade/Customer/Incident data — this table, and the
    review/dismiss status on it, is the entire footprint of that feature."""
    __tablename__ = "ai_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # "fixed_but_open" | "cross_signal" — see observation_signals.py for what
    # each candidate set means.
    kind: Mapped[str] = mapped_column(String(30))

    # The model's own one-sentence narration — never the detection itself,
    # which is computed deterministically before the model ever sees it.
    summary: Mapped[str] = mapped_column(Text)

    # Comma-joined jira_ref/customer ids this observation points at — same
    # convention as Case.linked_vms_refs/related_case_refs (no join table).
    # Every value here was already a real ref in the candidate set handed to
    # the model, never something the model introduced on its own.
    refs: Mapped[str] = mapped_column(Text)

    customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("customers.id", ondelete="SET NULL"))

    # New -> Reviewed | Dismissed. A human review action, never anything
    # this feature sets on its own past creation.
    status: Mapped[str] = mapped_column(String(20), default="New")

    # e.g. "qwen3:4b" — traceability if the local model changes later.
    model_used: Mapped[str] = mapped_column(String(50))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped["Customer | None"] = relationship()


from app.models.customer import Customer  # noqa: E402
