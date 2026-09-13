"""add related_case_refs and vms bug dates

Revision ID: e4b0833d00f1
Revises: b4973e65d633
Create Date: 2026-08-26 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e4b0833d00f1'
down_revision: Union[str, None] = 'b4973e65d633'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cases', sa.Column('related_case_refs', sa.String(length=500), nullable=True))
    op.add_column('vms_bugs', sa.Column('jira_created_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('vms_bugs', sa.Column('jira_resolved_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('vms_bugs', 'jira_resolved_at')
    op.drop_column('vms_bugs', 'jira_created_at')
    op.drop_column('cases', 'related_case_refs')
