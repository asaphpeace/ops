"""add customers.jira_customer_field_value — persisted, discovered-once Jira
Customer-picklist option value, so customer_case_stats() never needs to
rediscover it via a bounded recent-tickets scan (confirmed live that scan
can silently miss an otherwise-active customer once other project activity
pushes them out of the ~2000-ticket recency window it searches)

Revision ID: b57106146784
Revises: c49bca7cf842
Create Date: 2026-08-29

"""
from alembic import op
import sqlalchemy as sa

revision = "b57106146784"
down_revision = "c49bca7cf842"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("jira_customer_field_value", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "jira_customer_field_value")
