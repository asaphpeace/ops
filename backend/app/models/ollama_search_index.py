from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class OllamaSearchIndex(Base):
    """Full-text-search fallback for chat retrieval (services/ollama_context.py)
    — rebuilt in full every ~30 minutes by services/ollama_index.py from the
    real source tables (cases, case_comments, vms_bugs, upgrades,
    migration_projects, releases, incidents, incident_remediations,
    ops_notes, campaigns). Deliberately NOT a vector-embedding index — real
    data volume (confirmed live: ~22,400 rows total, ~4.9MB of it
    case_comments) is well within what Postgres's built-in full-text search
    handles natively, and pgvector isn't even available on this Postgres
    image. `content_tsv` (added via raw SQL in the migration, since
    SQLAlchemy has no first-class tsvector type) is a GENERATED ALWAYS AS
    column — it self-maintains on every INSERT, so this model and the
    rebuild job never compute it themselves."""

    __tablename__ = "ollama_search_index"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # "case" | "case_comment" | "vms_bug" | "upgrade" | "migration_project" |
    # "release" | "incident" | "incident_remediation" | "ops_note" | "campaign"
    source_type: Mapped[str] = mapped_column(String(30), index=True)

    # jira_ref for case/case_comment/vms_bug (case_comment uses
    # "<jira_ref>#<jira_comment_id>"), str(id) for everything else — same
    # comma-joined-ref-as-text convention as Case.linked_vms_refs, just one
    # ref per row here rather than comma-joined.
    source_ref: Mapped[str] = mapped_column(String(80))

    customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"))

    content: Mapped[str] = mapped_column(Text)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
