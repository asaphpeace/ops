"""Add incident severity/phase/post-incident-review fields, a third
mitigation remediation path, and Campaign.incident_id.

Part of the incident-response-maturity work grounded in real research
(NIST SP 800-61, SEV classification, the Incident Commander model) applied
to the real "API key required" product incident (Incident id=4). Severity
is informational only, confirmed directly with the user — no automatic
gating tied to it.

Revision ID: 9cc36642f39e
Revises: 23ee4ee80f33
Create Date: 2026-09-03

"""
from alembic import op
import sqlalchemy as sa

revision = "9cc36642f39e"
down_revision = "23ee4ee80f33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("severity", sa.String(20), nullable=False, server_default="Medium"))
    op.add_column("incidents", sa.Column("phase", sa.String(30), nullable=False, server_default="Detected"))
    op.add_column("incidents", sa.Column("lessons_learned", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("detection_gap", sa.Text(), nullable=True))

    op.add_column("incident_remediations", sa.Column("mitigation_type", sa.String(30), nullable=True))
    op.add_column("incident_remediations", sa.Column("mitigation_owner", sa.String(150), nullable=True))
    op.add_column("incident_remediations", sa.Column("mitigation_note", sa.Text(), nullable=True))
    op.add_column("incident_remediations", sa.Column("review_by_date", sa.Date(), nullable=True))

    op.add_column("campaigns", sa.Column("incident_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_campaigns_incident_id", "campaigns", "incidents", ["incident_id"], ["id"], ondelete="SET NULL",
    )

    # Every already-resolved incident is treated as already Closed (not
    # left at the "Detected" default) — a resolved incident sitting at
    # "Detected" would look like it was never diagnosed.
    op.execute("UPDATE incidents SET phase = 'Closed' WHERE status = 'Resolved'")


def downgrade() -> None:
    op.drop_constraint("fk_campaigns_incident_id", "campaigns", type_="foreignkey")
    op.drop_column("campaigns", "incident_id")

    op.drop_column("incident_remediations", "review_by_date")
    op.drop_column("incident_remediations", "mitigation_note")
    op.drop_column("incident_remediations", "mitigation_owner")
    op.drop_column("incident_remediations", "mitigation_type")

    op.drop_column("incidents", "detection_gap")
    op.drop_column("incidents", "lessons_learned")
    op.drop_column("incidents", "phase")
    op.drop_column("incidents", "severity")
