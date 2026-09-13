"""add cases.raw_status — the real Jira status string, for Case Mix by Status

Revision ID: dfcfe3027333
Revises: 77496a635bdd
Create Date: 2026-08-26

"""
from alembic import op
import sqlalchemy as sa

revision = "dfcfe3027333"
down_revision = "77496a635bdd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("raw_status", sa.String(60), nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "raw_status")
