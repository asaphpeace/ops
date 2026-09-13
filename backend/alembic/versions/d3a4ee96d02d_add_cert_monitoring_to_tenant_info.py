"""add cert monitoring to tenant info

Revision ID: d3a4ee96d02d
Revises: 106816cfa6f0
Create Date: 2026-09-11

"""
from alembic import op
import sqlalchemy as sa

revision = "d3a4ee96d02d"
down_revision = "106816cfa6f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customer_tenant_info", sa.Column("cert_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("customer_tenant_info", sa.Column("cert_issuer", sa.String(300), nullable=True))
    op.add_column("customer_tenant_info", sa.Column("cert_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("customer_tenant_info", sa.Column("cert_check_error", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("customer_tenant_info", "cert_check_error")
    op.drop_column("customer_tenant_info", "cert_checked_at")
    op.drop_column("customer_tenant_info", "cert_issuer")
    op.drop_column("customer_tenant_info", "cert_expires_at")
