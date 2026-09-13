"""Add Ollama chat tables: persisted conversations/messages, a call-metrics
log (real duration/token counts from Ollama's own response, shared by both
the supervisor's narration calls and interactive chat), and a full-text
search index (Postgres native tsvector/GIN, no pgvector — not available on
this Postgres image, and real data volume doesn't need vector embeddings:
confirmed live, ~22,400 indexable rows total, dominated by case_comments).

Revision ID: 23c1fe12835f
Revises: 967854b5b05f
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa

revision = "23c1fe12835f"
down_revision = "967854b5b05f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ollama_conversations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "ollama_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "conversation_id", sa.Integer,
            sa.ForeignKey("ollama_conversations.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("context_used", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_ollama_messages_conversation_id", "ollama_messages", ["conversation_id"])

    op.create_table(
        "ollama_call_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("model_used", sa.String(50), nullable=False),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("prompt_eval_count", sa.Integer, nullable=True),
        sa.Column("eval_count", sa.Integer, nullable=True),
        sa.Column(
            "conversation_id", sa.Integer,
            sa.ForeignKey("ollama_conversations.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_ollama_call_logs_created_at", "ollama_call_logs", ["created_at"])

    op.create_table(
        "ollama_search_index",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_ref", sa.String(80), nullable=False),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_ollama_search_index_source", "ollama_search_index", ["source_type"])
    op.create_index("ix_ollama_search_index_customer", "ollama_search_index", ["customer_id"])

    # No native tsvector type in SQLAlchemy — raw SQL. GENERATED ALWAYS AS
    # ... STORED means this column self-maintains on every INSERT, so the
    # rebuild job in services/ollama_index.py never computes it itself.
    # Generated columns are core Postgres >=12 (confirmed available on
    # postgres:16-alpine) — unlike pgvector, no extension needed.
    op.execute(
        "ALTER TABLE ollama_search_index ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
    )
    op.execute("CREATE INDEX ix_ollama_search_index_tsv ON ollama_search_index USING GIN (content_tsv)")


def downgrade() -> None:
    op.drop_table("ollama_search_index")
    op.drop_table("ollama_call_logs")
    op.drop_index("ix_ollama_messages_conversation_id", table_name="ollama_messages")
    op.drop_table("ollama_messages")
    op.drop_table("ollama_conversations")
