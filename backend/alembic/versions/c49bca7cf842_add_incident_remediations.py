"""add incident_remediations + incidents.linked_vms_ref

Revision ID: c49bca7cf842
Revises: e5a410456b8d
Create Date: 2026-08-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c49bca7cf842'
down_revision: Union[str, None] = 'e5a410456b8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('incidents', sa.Column('linked_vms_ref', sa.String(length=30), nullable=True))

    op.create_table(
        'incident_remediations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('incident_id', sa.Integer(), sa.ForeignKey('incidents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('upgrade_id', sa.Integer(), sa.ForeignKey('upgrades.id', ondelete='SET NULL'), nullable=True),
        sa.Column('manually_resolved', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('incident_id', 'customer_id', name='uq_incident_customer'),
    )
    op.create_index('ix_incident_remediations_incident_id', 'incident_remediations', ['incident_id'])
    op.create_index('ix_incident_remediations_customer_id', 'incident_remediations', ['customer_id'])


def downgrade() -> None:
    op.drop_index('ix_incident_remediations_customer_id', table_name='incident_remediations')
    op.drop_index('ix_incident_remediations_incident_id', table_name='incident_remediations')
    op.drop_table('incident_remediations')
    op.drop_column('incidents', 'linked_vms_ref')
