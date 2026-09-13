"""add cases.rovo_context/rovo_context_at and vms_bugs.rovo_context/
rovo_context_at — manual, zero-cost paste-in field for context gathered
outside the app (e.g. asking Rovo Chat in the Jira UI), folded into the
AI summarizers' local context in services/digest.py independent of whether
live Rovo MCP credentials are configured. Deliberately separate from
Case.resolution_note, which means "what actually fixed this" — a distinct
concept.

Revision ID: 5f8d14931faf
Revises: b57106146784
Create Date: 2026-08-31

"""
from alembic import op
import sqlalchemy as sa

revision = "5f8d14931faf"
down_revision = "b57106146784"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("rovo_context", sa.Text(), nullable=True))
    op.add_column("cases", sa.Column("rovo_context_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("vms_bugs", sa.Column("rovo_context", sa.Text(), nullable=True))
    op.add_column("vms_bugs", sa.Column("rovo_context_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("vms_bugs", "rovo_context_at")
    op.drop_column("vms_bugs", "rovo_context")
    op.drop_column("cases", "rovo_context_at")
    op.drop_column("cases", "rovo_context")
