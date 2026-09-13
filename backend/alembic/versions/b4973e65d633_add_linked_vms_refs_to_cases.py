"""add linked_vms_refs to cases

Revision ID: b4973e65d633
Revises: d3e4f5a6b7c8
Create Date: 2026-08-26 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4973e65d633'
down_revision: Union[str, None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cases', sa.Column('linked_vms_refs', sa.String(length=300), nullable=True))

    # Backfill so existing single-linked cases aren't left with an empty
    # plural column — mirrors the after-hours Premier backfill precedent
    # in the prior migration (d3e4f5a6b7c8).
    op.execute("UPDATE cases SET linked_vms_refs = linked_vms_ref WHERE linked_vms_ref IS NOT NULL")


def downgrade() -> None:
    op.drop_column('cases', 'linked_vms_refs')
