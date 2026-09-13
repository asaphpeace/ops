"""Add knowledge_extracts (categorized insights mined from OpsNote Slack
pastes by the local Ollama model) and ops_notes.knowledge_extracted_at
(tracks which notes have been processed).

Revision ID: 455f86d55e01
Revises: 23c1fe12835f
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa

revision = "455f86d55e01"
down_revision = "23c1fe12835f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ops_notes", sa.Column("knowledge_extracted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "knowledge_extracts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column(
            "source_note_id", sa.Integer,
            sa.ForeignKey("ops_notes.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("model_used", sa.String(50), nullable=False),
        sa.Column("dismissed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_knowledge_extracts_source_note_id", "knowledge_extracts", ["source_note_id"])
    op.create_index("ix_knowledge_extracts_category", "knowledge_extracts", ["category"])


def downgrade() -> None:
    op.drop_table("knowledge_extracts")
    op.drop_column("ops_notes", "knowledge_extracted_at")
