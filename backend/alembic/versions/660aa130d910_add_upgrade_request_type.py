"""Add upgrades.request_type — the originating ticket's real Jira Request
Type, captured once at creation time in _ensure_upgrade_from_ticket(). This
replaces pipeline_summary()'s prior approach of cross-referencing a local
Case row's request_type, which never worked for genuine sys-admin upgrades:
Case creation is deliberately skipped for Upgrade-classified tickets, so
that cross-reference silently hid every real, newly-created sys-admin
upgrade from the Kanban filter shipped earlier this session. Backfilled
from jira_unmatched where a matching row still exists (Upgrade/SSO-bridged
tickets are never deleted from jira_unmatched, so this covers essentially
every row created via the auto-bridge) — rows with no match stay NULL and
are correctly excluded from the Kanban, consistent with this session's
decision to relegate the historical Pending-Upgrade-sourced population to
the Releases > Pending Upgrade Queue instead.

Revision ID: 660aa130d910
Revises: 2eaf28b8d6c1
Create Date: 2026-09-03

"""
from alembic import op
import sqlalchemy as sa

revision = "660aa130d910"
down_revision = "2eaf28b8d6c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("upgrades", sa.Column("request_type", sa.String(length=100), nullable=True))
    op.execute(
        """
        UPDATE upgrades u
        SET request_type = j.request_type
        FROM jira_unmatched j
        WHERE u.jira_ref = j.jira_ref
          AND u.request_type IS NULL
          AND j.request_type IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("upgrades", "request_type")
