"""phase2_foundation: case timestamps + blocked_by + assignment + audit_log

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-08-21

"""
from alembic import op
import sqlalchemy as sa

revision = "b3c4d5e6f7a8"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extend cases ────────────────────────────────────────────────────────
    op.add_column("cases", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cases", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cases", sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cases", sa.Column("blocked_by", sa.String(50), nullable=True))
    op.add_column("cases", sa.Column("assigned_to", sa.String(200), nullable=True))
    op.add_column("cases", sa.Column("follow_up_due", sa.Date(), nullable=True))
    op.add_column("cases", sa.Column("resolution_note", sa.Text(), nullable=True))

    # ── Audit log table ──────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.String(100), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_log_action_target_ts",
        "audit_log",
        ["action", "target_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_action_target_ts", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_column("cases", "resolution_note")
    op.drop_column("cases", "follow_up_due")
    op.drop_column("cases", "assigned_to")
    op.drop_column("cases", "blocked_by")
    op.drop_column("cases", "escalated_at")
    op.drop_column("cases", "status_changed_at")
    op.drop_column("cases", "resolved_at")
