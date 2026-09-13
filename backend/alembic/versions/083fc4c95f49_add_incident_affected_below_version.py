"""add incidents.affected_below_version — a directly-known fix threshold
("any customer below this version is affected"), independent of
linked_vms_ref/VmsBug.fix_version, driving both manual suggestions and
automatic match-on-sync.

Revision ID: 083fc4c95f49
Revises: 8a59ef461320
Create Date: 2026-09-01

"""
from alembic import op
import sqlalchemy as sa

revision = "083fc4c95f49"
down_revision = "8a59ef461320"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("affected_below_version", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("incidents", "affected_below_version")
