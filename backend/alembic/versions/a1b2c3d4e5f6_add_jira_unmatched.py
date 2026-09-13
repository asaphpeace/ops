"""add jira_unmatched table

Revision ID: a1b2c3d4e5f6
Revises: b3f7e91c2d04
Create Date: 2026-08-21 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "b3f7e91c2d04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jira_unmatched",
        sa.Column("jira_ref", sa.String(30), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False, server_default=""),
        sa.Column("issue_type", sa.String(50), nullable=False, server_default=""),
        sa.Column("case_type", sa.String(30), nullable=False, server_default="Support"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="Medium"),
        sa.Column("labels", sa.String(500), nullable=False, server_default=""),
        sa.Column("days_open", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("jira_unmatched")
