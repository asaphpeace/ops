"""add customers.last_case_activity_at — real last-support-case date,
refreshed weekly from live Jira, backing the two-tier Quiet (6mo) / Dormant
(12mo) engagement flags on Customer Intelligence.

Revision ID: 8a59ef461320
Revises: 7248f0bdd95d
Create Date: 2026-09-01

"""
from alembic import op
import sqlalchemy as sa

revision = "8a59ef461320"
down_revision = "7248f0bdd95d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("last_case_activity_at", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "last_case_activity_at")
