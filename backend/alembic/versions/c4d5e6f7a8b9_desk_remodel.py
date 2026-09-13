"""desk_remodel: needs_csm_briefing + comment_count on cases, daily_case_snapshot table

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-24

"""
from alembic import op
import sqlalchemy as sa

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("needs_csm_briefing", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("cases", sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "daily_case_snapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("open_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("closed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_daily_case_snapshot_snapshot_date", "daily_case_snapshot", ["snapshot_date"])
    op.create_index("ix_daily_case_snapshot_customer_id", "daily_case_snapshot", ["customer_id"])
    op.create_index(
        "ix_snapshot_date_customer",
        "daily_case_snapshot",
        ["snapshot_date", "customer_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_snapshot_date_customer", table_name="daily_case_snapshot")
    op.drop_index("ix_daily_case_snapshot_customer_id", table_name="daily_case_snapshot")
    op.drop_index("ix_daily_case_snapshot_snapshot_date", table_name="daily_case_snapshot")
    op.drop_table("daily_case_snapshot")
    op.drop_column("cases", "comment_count")
    op.drop_column("cases", "needs_csm_briefing")
