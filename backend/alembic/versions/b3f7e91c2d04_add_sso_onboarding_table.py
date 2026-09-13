"""add_sso_onboarding_table

Revision ID: b3f7e91c2d04
Revises: 143d70e75e2e
Create Date: 2026-08-19 16:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b3f7e91c2d04'
down_revision: Union[str, None] = '143d70e75e2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sso_onboarding',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('has_prod', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('has_test', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('stage', sa.String(length=30), nullable=False, server_default='Not Started'),
        sa.Column('it_contact_name', sa.String(length=150), nullable=True),
        sa.Column('it_contact_email', sa.String(length=200), nullable=True),
        sa.Column('email_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('guest_invite_sent', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('reply_received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('field_domain', sa.String(length=200), nullable=True),
        sa.Column('field_client_id', sa.String(length=200), nullable=True),
        sa.Column('field_secret', sa.String(length=200), nullable=True),
        sa.Column('field_reply_url', sa.String(length=500), nullable=True),
        sa.Column('field_app_id_uri', sa.String(length=500), nullable=True),
        sa.Column('devops_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('switchover_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('switchover_duration_mins', sa.Integer(), nullable=True),
        sa.Column('follow_up_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('customer_id'),
    )
    op.create_index('ix_sso_onboarding_customer_id', 'sso_onboarding', ['customer_id'])


def downgrade() -> None:
    op.drop_index('ix_sso_onboarding_customer_id', table_name='sso_onboarding')
    op.drop_table('sso_onboarding')
