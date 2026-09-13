"""add jira_unmatched dismissed flag

Revision ID: 1ba843bc356a
Revises: adc8edf88658
Create Date: 2026-08-27 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1ba843bc356a'
down_revision: Union[str, None] = 'adc8edf88658'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'jira_unmatched',
        sa.Column('dismissed', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('jira_unmatched', 'dismissed')
