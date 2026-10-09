"""add automation runs (Tools → Upgrade Runner)

Revision ID: 1aa6c6290a7d
Revises: 47e4ba5efc6f
Create Date: 2026-10-06

"""
from alembic import op
import sqlalchemy as sa

revision = "1aa6c6290a7d"
down_revision = "47e4ba5efc6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("environment", sa.String(100), nullable=True),
        sa.Column("from_version", sa.String(40), nullable=True),
        sa.Column("target_version", sa.String(40), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("dry_run_of_id", sa.Integer(), sa.ForeignKey("automation_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("runner_job_id", sa.String(40), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("log", sa.Text(), nullable=False, server_default=""),
        sa.Column("log_line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("post_check_release", sa.String(40), nullable=True),
        sa.Column("post_check_ok", sa.Boolean(), nullable=True),
        sa.Column("post_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor", sa.String(200), nullable=False, server_default="you"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_automation_runs_started_at", "automation_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_automation_runs_started_at", table_name="automation_runs")
    op.drop_table("automation_runs")
