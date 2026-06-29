"""dataset export jobs + task operation log

Revision ID: 20260629_0013
Revises: 20260629_0012
Create Date: 2026-06-29 04:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '20260629_0013'
down_revision = '20260629_0012'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dataset_export_jobs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('task_type_id', sa.String(64), nullable=False),
        sa.Column('export_format', sa.String(16), nullable=False),
        sa.Column('episode_count', sa.Integer(), nullable=False),
        sa.Column('filters_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('created_by', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), server_default=sa.func.now()),
    )

    op.create_table(
        'task_operation_log',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('task_id', sa.String(64), nullable=False, index=True),
        sa.Column('episode_id', sa.String(64), nullable=False),
        sa.Column('operation', sa.String(32), nullable=False),
        sa.Column('from_reviewer', sa.String(64), nullable=False, server_default=''),
        sa.Column('to_reviewer', sa.String(64), nullable=False, server_default=''),
        sa.Column('operator_id', sa.String(64), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=False), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('task_operation_log')
    op.drop_table('dataset_export_jobs')
