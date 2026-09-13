"""add upgrades.linked_vms_ref — the real VMS bug a manually-created
upgrade exists to fix, when known. Drives the new overdue bug-fix-upgrade
supervision logic (My Desk Flags row + Release Intelligence).

Revision ID: a4d5041d3080
Revises: 083fc4c95f49
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa

revision = "a4d5041d3080"
down_revision = "083fc4c95f49"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("upgrades", sa.Column("linked_vms_ref", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("upgrades", "linked_vms_ref")
