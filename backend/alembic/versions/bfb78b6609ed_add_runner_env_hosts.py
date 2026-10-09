"""add runner env hosts (public host for unlinked aws-util environments)

Revision ID: bfb78b6609ed
Revises: ab077f354e0c
Create Date: 2026-10-09

"""
from alembic import op
import sqlalchemy as sa

revision = "bfb78b6609ed"
down_revision = "ab077f354e0c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runner_env_hosts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("environment", sa.String(100), nullable=False, unique=True),
        sa.Column("host", sa.String(300), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("runner_env_hosts")
