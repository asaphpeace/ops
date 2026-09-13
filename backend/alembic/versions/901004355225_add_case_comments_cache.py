"""add case_comments table — local cache of Jira comment/activity history so
fetch_case_activity() can do a cheap total-count freshness check against
Jira instead of re-downloading the whole comment thread on every tab open.

Revision ID: 901004355225
Revises: 5f8d14931faf
Create Date: 2026-08-31

"""
from alembic import op
import sqlalchemy as sa

revision = "901004355225"
down_revision = "5f8d14931faf"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jira_comment_id", sa.String(length=30), nullable=False),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column("created", sa.DateTime(timezone=True), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("public", sa.Boolean(), nullable=True),
        sa.UniqueConstraint("case_id", "jira_comment_id", name="uq_case_comment"),
    )
    op.create_index("ix_case_comments_case_id", "case_comments", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_case_comments_case_id", table_name="case_comments")
    op.drop_table("case_comments")
