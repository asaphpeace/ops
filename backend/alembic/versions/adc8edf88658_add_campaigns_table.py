"""add campaigns table

Revision ID: adc8edf88658
Revises: dd9bac031822
Create Date: 2026-08-27 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'adc8edf88658'
down_revision: Union[str, None] = 'dd9bac031822'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'campaigns',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('customer_ids', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='Draft'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('campaigns')
