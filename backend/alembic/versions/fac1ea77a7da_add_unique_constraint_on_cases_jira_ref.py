"""add unique constraint on cases.jira_ref

Revision ID: fac1ea77a7da
Revises: 2e29f1a83bd5
Create Date: 2026-08-25 16:52:06.431875

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'fac1ea77a7da'
down_revision: Union[str, None] = '2e29f1a83bd5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_cases_jira_ref', table_name='cases')
    op.create_index(op.f('ix_cases_jira_ref'), 'cases', ['jira_ref'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_cases_jira_ref'), table_name='cases')
    op.create_index('ix_cases_jira_ref', 'cases', ['jira_ref'], unique=False)
