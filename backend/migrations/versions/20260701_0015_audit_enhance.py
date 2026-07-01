"""enhance audit_events with event_type, severity, operator_id, ip_address, user_agent, duration_ms

Revision ID: 20260701_0015
Revises: 20260629_0014
Create Date: 2026-07-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '20260701_0015'
down_revision = '20260629_0014'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('audit_events', sa.Column('event_type', sa.String(32), nullable=False, server_default='business_action'))
    op.add_column('audit_events', sa.Column('severity', sa.String(16), nullable=False, server_default='info'))
    op.add_column('audit_events', sa.Column('operator_id', sa.String(64), nullable=True))
    op.add_column('audit_events', sa.Column('ip_address', sa.String(45), nullable=True))
    op.add_column('audit_events', sa.Column('user_agent', sa.String(256), nullable=True))
    op.add_column('audit_events', sa.Column('duration_ms', sa.Integer, nullable=True))


def downgrade():
    op.drop_column('audit_events', 'duration_ms')
    op.drop_column('audit_events', 'user_agent')
    op.drop_column('audit_events', 'ip_address')
    op.drop_column('audit_events', 'operator_id')
    op.drop_column('audit_events', 'severity')
    op.drop_column('audit_events', 'event_type')
