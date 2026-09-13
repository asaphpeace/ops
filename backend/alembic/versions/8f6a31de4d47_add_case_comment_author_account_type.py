"""Add case_comments.author_account_type — the real signal for whether a
public (jsdPublic=True) comment was actually written by the customer or by
a team member replying publicly. Fixes a real bug: last-reply detection
was treating every public comment as customer-authored, mislabeling real
team replies (e.g. Gisele Wolff, accountType="atlassian") as "customer".

Revision ID: 8f6a31de4d47
Revises: 91f0faaaec61
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa

revision = "8f6a31de4d47"
down_revision = "91f0faaaec61"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("case_comments", sa.Column("author_account_type", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("case_comments", "author_account_type")
