"""add source_jira_ref to sso_onboarding

Revision ID: 0425efa33148
Revises: e4b0833d00f1
Create Date: 2026-08-26 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0425efa33148'
down_revision: Union[str, None] = 'e4b0833d00f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sso_onboarding', sa.Column('source_jira_ref', sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column('sso_onboarding', 'source_jira_ref')
