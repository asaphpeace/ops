"""add verified versions (Upgrade Runner remembered release checks)

Revision ID: ab077f354e0c
Revises: 1aa6c6290a7d
Create Date: 2026-10-06

"""
from alembic import op
import sqlalchemy as sa

revision = "ab077f354e0c"
down_revision = "1aa6c6290a7d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verified_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(40), nullable=False, unique=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("verified_by", sa.String(200), nullable=False, server_default="you"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("verified_versions")
