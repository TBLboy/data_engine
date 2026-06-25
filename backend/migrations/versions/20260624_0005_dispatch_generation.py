"""task dispatch generation versioning

Revision ID: 20260624_0005
Revises: 20260624_0004
Create Date: 2026-06-24 19:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260624_0005'
down_revision = '20260624_0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('batches', sa.Column('active_dispatch_generation', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('qc_tasks', sa.Column('dispatch_generation', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('qc_tasks', sa.Column('is_active', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('qc_tasks', sa.Column('assignment_mode', sa.String(length=32), nullable=False, server_default='manual'))


def downgrade() -> None:
    op.drop_column('qc_tasks', 'assignment_mode')
    op.drop_column('qc_tasks', 'is_active')
    op.drop_column('qc_tasks', 'dispatch_generation')
    op.drop_column('batches', 'active_dispatch_generation')
