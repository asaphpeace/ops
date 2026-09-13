"""add vms_api_credentials — M2M link foundation for querying a customer's
live Dataloy VMS (OAuth2 client-credentials, per api.dataloy.com docs)

Revision ID: dd9bac031822
Revises: dfcfe3027333
Create Date: 2026-08-27

"""
from alembic import op
import sqlalchemy as sa

revision = "dd9bac031822"
down_revision = "dfcfe3027333"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vms_api_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("client_id", sa.String(200), nullable=False),
        sa.Column("client_secret", sa.String(500), nullable=False),
        sa.Column("audience", sa.String(50), nullable=False, server_default="https://dataloy"),
        sa.Column("cached_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id"),
    )


def downgrade() -> None:
    op.drop_table("vms_api_credentials")
