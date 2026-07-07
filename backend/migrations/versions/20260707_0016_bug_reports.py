"""add bug_reports table

Revision ID: 20260707_0016
Revises: 20260701_0015
Create Date: 2026-07-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '20260707_0016'
down_revision = '20260701_0015'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bug_reports',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='open'),
        sa.Column('image_filename', sa.String(length=255), nullable=True),
        sa.Column('image_content_type', sa.String(length=64), nullable=True),
        sa.Column('reporter_user_id', sa.String(length=64), nullable=False),
        sa.Column('reporter_name', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bug_reports_status', 'bug_reports', ['status'], unique=False)
    op.create_index('ix_bug_reports_reporter_user_id', 'bug_reports', ['reporter_user_id'], unique=False)


def downgrade():
    op.drop_index('ix_bug_reports_reporter_user_id', table_name='bug_reports')
    op.drop_index('ix_bug_reports_status', table_name='bug_reports')
    op.drop_table('bug_reports')
