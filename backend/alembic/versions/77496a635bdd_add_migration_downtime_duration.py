"""add migration downtime duration

Revision ID: 77496a635bdd
Revises: 0425efa33148
Create Date: 2026-08-26 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '77496a635bdd'
down_revision: Union[str, None] = '0425efa33148'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('migration_projects', sa.Column('downtime_duration_mins', sa.Integer(), nullable=False, server_default='240'))


def downgrade() -> None:
    op.drop_column('migration_projects', 'downtime_duration_mins')
