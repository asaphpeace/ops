"""Add upgrades.devops_confirmed_at / upgrades.customer_confirmed_at — real,
distinct confirmation timestamps for each party. The existing confirmed_at
column is dead (no live write path ever sets it, only seed.py fixtures) and
was never two-party anyway; kept untouched, not repurposed, to avoid any
risk to UpgradeUpdate/UpgradeOut's existing shape.

Revision ID: 2eaf28b8d6c1
Revises: f8a3d505641b
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa

revision = "2eaf28b8d6c1"
down_revision = "f8a3d505641b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("upgrades", sa.Column("devops_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("upgrades", sa.Column("customer_confirmed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("upgrades", "customer_confirmed_at")
    op.drop_column("upgrades", "devops_confirmed_at")
