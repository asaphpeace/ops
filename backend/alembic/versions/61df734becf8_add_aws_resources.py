"""Add aws_resources + aws_resource_metric_snapshots — real AWS compute/DB
inventory ingested from a periodic manual export (never a live boto3
poller), matched to customers via a name-heuristic that always requires a
human confirmation, mirroring tenant_discovery.py's probe-then-Accept
flow. See services/aws_import.py and routers/engineering.py.

Revision ID: 61df734becf8
Revises: e2071908dd96
Create Date: 2026-09-07

"""
from alembic import op
import sqlalchemy as sa

revision = "61df734becf8"
down_revision = "e2071908dd96"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "aws_resources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resource_type", sa.String(length=10), nullable=False),
        sa.Column("resource_id", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=200)),
        sa.Column("region", sa.String(length=20)),
        sa.Column("aws_environment", sa.String(length=10), nullable=False),
        sa.Column("instance_type", sa.String(length=30)),
        sa.Column("engine", sa.String(length=50)),
        sa.Column("engine_version", sa.String(length=30)),
        sa.Column("state", sa.String(length=30)),
        sa.Column("endpoint_or_ip", sa.String(length=200)),
        sa.Column("launched_at", sa.DateTime(timezone=True)),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL")),
        sa.Column("customer_environment", sa.String(length=10)),
        sa.Column("suggested_customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL")),
        sa.Column("match_status", sa.String(length=20), nullable=False, server_default="unmatched"),
        sa.Column("match_method", sa.String(length=20)),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("resource_type", "resource_id", "aws_environment", name="uq_aws_resource"),
    )

    op.create_table(
        "aws_resource_metric_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("aws_resource_id", sa.Integer(), sa.ForeignKey("aws_resources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cpu_utilization_pct", sa.Float()),
        sa.Column("raw_json", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_aws_resource_metric_snapshots_resource", "aws_resource_metric_snapshots", ["aws_resource_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_aws_resource_metric_snapshots_resource", table_name="aws_resource_metric_snapshots")
    op.drop_table("aws_resource_metric_snapshots")
    op.drop_table("aws_resources")
