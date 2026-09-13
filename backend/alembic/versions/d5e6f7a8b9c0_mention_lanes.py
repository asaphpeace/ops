"""mention_lanes: last_mention tracking, lane_override, first_public_reply_at on cases

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-24

"""
from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("last_mention_name", sa.String(200), nullable=True))
    op.add_column("cases", sa.Column("last_mention_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cases", sa.Column("lane_override", sa.String(20), nullable=True))
    op.add_column("cases", sa.Column("first_public_reply_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "first_public_reply_at")
    op.drop_column("cases", "lane_override")
    op.drop_column("cases", "last_mention_at")
    op.drop_column("cases", "last_mention_name")
