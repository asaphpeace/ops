"""Add customer_tenant_info.self_serviceable and upgrades.devops_engineer.

self_serviceable marks a real (customer, environment) pair the user can
personally run the upgrade against (via their own internal environment
tool), bypassing DevOps entirely. Backfilled here against 55 real pairs
confirmed live this session by cross-referencing a screenshot of that
tool's environment list against customer_tenant_info's own subdomains
(exact-match prioritized over substring, after catching a real false
positive — "peak-test" initially matched "Seapeak" instead of "Peak People
AS" via a loose substring check).

devops_engineer records which of the two real DevOps engineers (Martin
Fure / Elias Hjellestad) is responsible for a non-self-service upgrade —
separate from devops_confirmed_at, which only tracks whether a slot has
been confirmed, not by whom.

Revision ID: 23ee4ee80f33
Revises: 660aa130d910
Create Date: 2026-09-03

"""
from alembic import op
import sqlalchemy as sa

revision = "23ee4ee80f33"
down_revision = "660aa130d910"
branch_labels = None
depends_on = None

# (customer_id, environment) — confirmed live against customer_tenant_info.
_SELF_SERVICE_PAIRS = [
    (110, "PROD"), (110, "TEST"), (531, "TEST"), (456, "DEV"), (456, "PROD"),
    (456, "TEST"), (525, "PROD"), (525, "TEST"), (85, "PROD"), (85, "TEST"),
    (552, "TEST"), (539, "DEV"), (539, "TEST"), (465, "PROD"), (465, "TEST"),
    (535, "TEST"), (521, "PROD"), (521, "TEST"), (54, "PROD"), (187, "DEV"),
    (205, "PROD"), (526, "TEST"), (95, "PROD"), (95, "TEST"), (147, "PROD"),
    (534, "TEST"), (537, "PROD"), (537, "TEST"), (459, "TEST"), (458, "TEST"),
    (467, "PROD"), (560, "PROD"), (510, "PROD"), (510, "TEST"), (454, "PROD"),
    (454, "TEST"), (51, "PROD"), (51, "TEST"), (530, "PROD"), (530, "TEST"),
    (462, "TEST"), (533, "PROD"), (533, "TEST"), (64, "TEST"), (460, "TEST"),
    (265, "PROD"), (453, "DEV"), (453, "PROD"), (453, "TEST"), (461, "DEV"),
    (461, "TEST"), (67, "TEST"), (529, "DEV"), (529, "TEST"), (3, "PROD"),
]


def upgrade() -> None:
    op.add_column(
        "customer_tenant_info",
        sa.Column("self_serviceable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("upgrades", sa.Column("devops_engineer", sa.String(length=100), nullable=True))

    conn = op.get_bind()
    for customer_id, environment in _SELF_SERVICE_PAIRS:
        conn.execute(
            sa.text(
                "UPDATE customer_tenant_info SET self_serviceable = true "
                "WHERE customer_id = :cid AND environment = :env"
            ),
            {"cid": customer_id, "env": environment},
        )


def downgrade() -> None:
    op.drop_column("upgrades", "devops_engineer")
    op.drop_column("customer_tenant_info", "self_serviceable")
