"""Add log_entries — a scoped substitute for a real log platform (not a
Humio/Falcon LogScale replica): real AWS log events (CloudWatch Logs +
CloudTrail) imported from a periodic manual export, full-text searchable
via Postgres tsvector (same precedent as ollama_search_index). See
services/log_import.py and routers/engineering.py.

Revision ID: aa5c64c8b634
Revises: 61df734becf8
Create Date: 2026-09-07

"""
from alembic import op
import sqlalchemy as sa

revision = "aa5c64c8b634"
down_revision = "61df734becf8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "log_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("log_type", sa.String(length=20), nullable=False),
        sa.Column("source_group", sa.String(length=200), nullable=False),
        sa.Column("event_id", sa.String(length=80), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("level", sa.String(length=20)),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.Column("aws_resource_id", sa.Integer(), sa.ForeignKey("aws_resources.id", ondelete="SET NULL")),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("log_type", "source_group", "event_id", name="uq_log_entry_event"),
    )
    op.create_index("ix_log_entries_log_type", "log_entries", ["log_type"])
    op.create_index("ix_log_entries_timestamp", "log_entries", ["timestamp"])
    op.create_index("ix_log_entries_aws_resource_id", "log_entries", ["aws_resource_id"])

    # No native tsvector type in SQLAlchemy — raw SQL, same precedent as
    # ollama_search_index.content_tsv. GENERATED ALWAYS AS ... STORED
    # self-maintains on every INSERT, so log_import.py never computes it.
    op.execute(
        "ALTER TABLE log_entries ADD COLUMN message_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', message)) STORED"
    )
    op.execute("CREATE INDEX ix_log_entries_message_tsv ON log_entries USING GIN (message_tsv)")


def downgrade() -> None:
    op.drop_index("ix_log_entries_message_tsv", table_name="log_entries")
    op.drop_index("ix_log_entries_aws_resource_id", table_name="log_entries")
    op.drop_index("ix_log_entries_timestamp", table_name="log_entries")
    op.drop_index("ix_log_entries_log_type", table_name="log_entries")
    op.drop_table("log_entries")
