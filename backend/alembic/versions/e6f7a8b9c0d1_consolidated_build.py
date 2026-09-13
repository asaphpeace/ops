"""consolidated_build: ttfr, jira_customer_name, vms_bugs, ai summaries, calendar fields

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-08-25

"""
from alembic import op
import sqlalchemy as sa

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Phase 1 — real TTFR + customer identity
    op.add_column("cases", sa.Column("ttfr_hours", sa.Float(), nullable=True))
    op.add_column("cases", sa.Column("ttfr_breached", sa.Boolean(), nullable=True))
    op.add_column("cases", sa.Column("jira_customer_name", sa.String(200), nullable=True))
    op.add_column("jira_unmatched", sa.Column("jira_customer_name", sa.String(200), nullable=True))

    # Phase 3 — VMS bug linkage
    op.add_column("cases", sa.Column("linked_vms_ref", sa.String(30), nullable=True))
    op.create_table(
        "vms_bugs",
        sa.Column("jira_ref", sa.String(30), nullable=False),
        sa.Column("issue_type", sa.String(50), nullable=False, server_default=""),
        sa.Column("status", sa.String(50), nullable=False, server_default=""),
        sa.Column("fix_version", sa.String(50), nullable=True),
        sa.Column("labels", sa.String(500), nullable=False, server_default=""),
        sa.Column("ai_summary", sa.String(2000), nullable=True),
        sa.Column("ai_summary_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("jira_ref"),
    )

    # Phase 4 — cached AI customer summary
    op.add_column("customers", sa.Column("ai_summary", sa.Text(), nullable=True))
    op.add_column("customers", sa.Column("ai_summary_at", sa.DateTime(timezone=True), nullable=True))

    # Phase 6 — Google Calendar (internal-only, one-way push)
    op.add_column("upgrades", sa.Column("google_event_id", sa.String(200), nullable=True))
    op.add_column("upgrades", sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="120"))


def downgrade() -> None:
    op.drop_column("upgrades", "duration_minutes")
    op.drop_column("upgrades", "google_event_id")
    op.drop_column("customers", "ai_summary_at")
    op.drop_column("customers", "ai_summary")
    op.drop_table("vms_bugs")
    op.drop_column("cases", "linked_vms_ref")
    op.drop_column("jira_unmatched", "jira_customer_name")
    op.drop_column("cases", "jira_customer_name")
    op.drop_column("cases", "ttfr_breached")
    op.drop_column("cases", "ttfr_hours")
