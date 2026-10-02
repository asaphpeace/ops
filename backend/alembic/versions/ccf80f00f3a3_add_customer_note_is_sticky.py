"""add customer_note is_sticky

Revision ID: ccf80f00f3a3
Revises: d3a4ee96d02d
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa

revision = "ccf80f00f3a3"
down_revision = "d3a4ee96d02d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customer_notes",
        sa.Column("is_sticky", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("customer_notes", "is_sticky")
