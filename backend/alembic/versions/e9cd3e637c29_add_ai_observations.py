"""add ai_observations — advisory-only findings from the local Ollama
supervisor (services/ollama_supervisor.py). Detection is computed
deterministically before the model ever sees it; this table only stores
the model's narration plus a human review/dismiss status.

Revision ID: e9cd3e637c29
Revises: a4d5041d3080
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa

revision = "e9cd3e637c29"
down_revision = "a4d5041d3080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("refs", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="New"),
        sa.Column("model_used", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ai_observations")
