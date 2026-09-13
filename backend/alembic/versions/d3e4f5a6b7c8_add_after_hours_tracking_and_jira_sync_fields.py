"""add after hours tracking and jira sync fields

Revision ID: d3e4f5a6b7c8
Revises: fac1ea77a7da
Create Date: 2026-08-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = 'fac1ea77a7da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('jira_unmatched', sa.Column('request_type', sa.String(length=100), nullable=True))
    op.add_column('cases', sa.Column('request_type', sa.String(length=100), nullable=True))

    op.add_column('vms_bugs', sa.Column('sprint_name', sa.String(length=100), nullable=True))
    op.add_column('vms_bugs', sa.Column('sprint_state', sa.String(length=20), nullable=True))
    op.add_column('vms_bugs', sa.Column('assignee', sa.String(length=200), nullable=True))

    op.add_column('customers', sa.Column('after_hours_eligible', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('customers', sa.Column('after_hours_limit', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('customers', sa.Column('after_hours_used', sa.Integer(), nullable=False, server_default='0'))

    op.add_column('upgrades', sa.Column('after_hours', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('upgrades', sa.Column('after_hours_billed_hours', sa.Float(), nullable=True))
    op.add_column('upgrades', sa.Column('after_hours_billing_note', sa.String(length=500), nullable=True))

    # Backfill existing Premier customers with the tier default rather than
    # leaving all of them "Not eligible" until their next PATCH — mirrors
    # why upgrades_limit needed active enforcement, not just a schema
    # default (see comment at routers/customers.py:213).
    op.execute("UPDATE customers SET after_hours_eligible = true, after_hours_limit = 4 WHERE tier = 'Premier'")


def downgrade() -> None:
    op.drop_column('upgrades', 'after_hours_billing_note')
    op.drop_column('upgrades', 'after_hours_billed_hours')
    op.drop_column('upgrades', 'after_hours')
    op.drop_column('customers', 'after_hours_used')
    op.drop_column('customers', 'after_hours_limit')
    op.drop_column('customers', 'after_hours_eligible')
    op.drop_column('vms_bugs', 'assignee')
    op.drop_column('vms_bugs', 'sprint_state')
    op.drop_column('vms_bugs', 'sprint_name')
    op.drop_column('cases', 'request_type')
    op.drop_column('jira_unmatched', 'request_type')
