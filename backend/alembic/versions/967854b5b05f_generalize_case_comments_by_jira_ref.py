"""Generalize case_comments to be keyed by jira_ref, not just case_id —
most tickets processed by the bulk aggregate functions (team_open_stats
etc.) have no local Case row at all, so the existing case_id-only cache
never applied to them. case_id becomes an optional back-reference;
lookup/dedup is now always by jira_ref. Backfills jira_ref for existing
rows from their case's own jira_ref.

Revision ID: 967854b5b05f
Revises: f16e63c2b125
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa

revision = "967854b5b05f"
down_revision = "f16e63c2b125"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("case_comments", sa.Column("jira_ref", sa.String(30), nullable=True))
    op.execute(
        "UPDATE case_comments SET jira_ref = cases.jira_ref "
        "FROM cases WHERE cases.id = case_comments.case_id"
    )
    op.alter_column("case_comments", "jira_ref", nullable=False)
    op.create_index("ix_case_comments_jira_ref", "case_comments", ["jira_ref"])

    op.alter_column("case_comments", "case_id", nullable=True)
    op.drop_constraint("uq_case_comment", "case_comments", type_="unique")
    op.create_unique_constraint("uq_case_comment_ref", "case_comments", ["jira_ref", "jira_comment_id"])


def downgrade() -> None:
    op.drop_constraint("uq_case_comment_ref", "case_comments", type_="unique")
    op.create_unique_constraint("uq_case_comment", "case_comments", ["case_id", "jira_comment_id"])
    op.alter_column("case_comments", "case_id", nullable=False)
    op.drop_index("ix_case_comments_jira_ref", table_name="case_comments")
    op.drop_column("case_comments", "jira_ref")
