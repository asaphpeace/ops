"""Add ollama_messages.model_used — tags which model produced an assistant
reply (the local Ollama model, or "claude-haiku-4-5" for an escalated
reply). Supports showing "via Ollama" / "via Claude" in the chat UI.

Revision ID: f8a3d505641b
Revises: 455f86d55e01
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa

revision = "f8a3d505641b"
down_revision = "455f86d55e01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ollama_messages", sa.Column("model_used", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("ollama_messages", "model_used")
