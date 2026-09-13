"""add ops_notes — manually-pasted operational context (e.g. Slack
discussion), not tied to a specific ticket. No Slack API access is
available, so this is a paste-in log, not a live sync.

Revision ID: f16e63c2b125
Revises: e9cd3e637c29
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa

revision = "f16e63c2b125"
down_revision = "e9cd3e637c29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ops_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_label", sa.String(100), nullable=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("jira_ref", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ops_notes")
