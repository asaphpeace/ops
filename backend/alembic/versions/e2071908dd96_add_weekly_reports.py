"""Add weekly_reports — a stored per-ISO-week snapshot of the fully
computed weekly ops report (Support/Bug/Upgrade/Migration/Incident impact
+ customers affected), used for the recurring DevOps priority meeting and
PDF export. Stores the computed content itself (JSON), not just metadata,
so a generated report stays stable if reopened later and week-over-week
trend has something fixed to diff against.

Revision ID: e2071908dd96
Revises: 8f6a31de4d47
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa

revision = "e2071908dd96"
down_revision = "8f6a31de4d47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weekly_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week", sa.String(length=10), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="Draft"),
        sa.Column("snapshot", sa.JSON(), nullable=False),
    )
    op.create_index("ix_weekly_reports_week", "weekly_reports", ["week"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_weekly_reports_week", table_name="weekly_reports")
    op.drop_table("weekly_reports")
