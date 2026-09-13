"""add customer_contacts table — structured per-customer email contact
list, populated from a real Jira/Confluence search across the validated
VMS customer list.

Revision ID: c41d64106ae5
Revises: 901004355225
Create Date: 2026-08-31

"""
from alembic import op
import sqlalchemy as sa

revision = "c41d64106ae5"
down_revision = "901004355225"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("customer_id", "email", name="uq_customer_contact_email"),
    )
    op.create_index("ix_customer_contacts_customer_id", "customer_contacts", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_customer_contacts_customer_id", table_name="customer_contacts")
    op.drop_table("customer_contacts")
