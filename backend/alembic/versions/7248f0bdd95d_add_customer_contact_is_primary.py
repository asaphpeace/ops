"""add customer_contacts.is_primary + primary_contact_reason — designates a
single main/technical contact per customer for outbound comms, instead of
sending to every stored contact (some customers have 40+).

Revision ID: 7248f0bdd95d
Revises: 75f7ba044fb5
Create Date: 2026-09-01

"""
from alembic import op
import sqlalchemy as sa

revision = "7248f0bdd95d"
down_revision = "75f7ba044fb5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customer_contacts", sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("customer_contacts", sa.Column("primary_contact_reason", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("customer_contacts", "primary_contact_reason")
    op.drop_column("customer_contacts", "is_primary")
