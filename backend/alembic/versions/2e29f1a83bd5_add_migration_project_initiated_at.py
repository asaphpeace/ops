"""add migration_project initiated_at

Revision ID: 2e29f1a83bd5
Revises: 6294c7e7e387
Create Date: 2026-08-25 16:27:02.079149

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2e29f1a83bd5'
down_revision: Union[str, None] = '6294c7e7e387'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('migration_projects', sa.Column('initiated_at', sa.DateTime(timezone=True), nullable=True))

    # Backfill: every pre-existing migration_project row was created by a
    # human explicitly clicking "+ Start Migration", so it's already
    # initiated. The exception is the batch of candidates imported from
    # Elias's real Old-AWS environment list — those default to NULL
    # (not yet initiated) so they land in the Migration Priority backlog,
    # not the kanban, identified by the exact notes string that import
    # script wrote, guarded by stage='Not Started' in case any were
    # already advanced since.
    op.execute("""
        UPDATE migration_projects
        SET initiated_at = created_at
        WHERE NOT (
            COALESCE(integration_notes, '') LIKE 'Old-AWS migration candidate%'
            AND stage = 'Not Started'
        )
    """)


def downgrade() -> None:
    op.drop_column('migration_projects', 'initiated_at')
