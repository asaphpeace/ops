"""add customers.jvm_client — flags customers still on the old Java
desktop client ("JVMS" in the validated VMS customer list) rather than
the modern web app, confirmed from the same validated source used for
the Contacts/product-tag correction pass.

Revision ID: 75f7ba044fb5
Revises: c41d64106ae5
Create Date: 2026-09-01

"""
from alembic import op
import sqlalchemy as sa

revision = "75f7ba044fb5"
down_revision = "c41d64106ae5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("jvm_client", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("customers", "jvm_client")
