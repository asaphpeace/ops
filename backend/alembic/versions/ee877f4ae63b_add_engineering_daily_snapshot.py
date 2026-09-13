"""add engineering daily snapshot

Revision ID: ee877f4ae63b
Revises: aa5c64c8b634
Create Date: 2026-09-08

"""
from alembic import op
import sqlalchemy as sa

revision = "ee877f4ae63b"
down_revision = "aa5c64c8b634"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "engineering_daily_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False, unique=True),
        sa.Column("estate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("on_current_release_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("customer_exposure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("legacy_footprint_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_engineering_daily_snapshot_snapshot_date", "engineering_daily_snapshot", ["snapshot_date"])


def downgrade() -> None:
    op.drop_index("ix_engineering_daily_snapshot_snapshot_date", table_name="engineering_daily_snapshot")
    op.drop_table("engineering_daily_snapshot")
