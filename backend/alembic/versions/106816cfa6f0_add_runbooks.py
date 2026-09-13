"""add runbooks

Revision ID: 106816cfa6f0
Revises: ee877f4ae63b
Create Date: 2026-09-08

"""
from alembic import op
import sqlalchemy as sa

revision = "106816cfa6f0"
down_revision = "ee877f4ae63b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runbooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ref", sa.String(20), nullable=False, unique=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("trigger_hosting_model", sa.String(30), nullable=True),
        sa.Column("trigger_engine_contains", sa.String(50), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("runbooks")
