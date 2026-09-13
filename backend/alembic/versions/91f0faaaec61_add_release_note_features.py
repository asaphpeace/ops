"""Add release_note_features — cached, real new-feature entries scraped
from releasenotes.dataloy.com's master-release Synopsis pages. Feeds the
Education view's version-driven training recommendations.

Revision ID: 91f0faaaec61
Revises: 9cc36642f39e
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa

revision = "91f0faaaec61"
down_revision = "9cc36642f39e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "release_note_features",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.String(30), nullable=False),
        sa.Column("ticket_id", sa.String(30), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("category", sa.String(150), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(300), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("version", "ticket_id", "title", name="uq_release_note_feature"),
    )
    op.create_index("ix_release_note_features_version", "release_note_features", ["version"])


def downgrade() -> None:
    op.drop_index("ix_release_note_features_version", table_name="release_note_features")
    op.drop_table("release_note_features")
