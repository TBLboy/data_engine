"""task type arm mode

Revision ID: 20260707_0017
Revises: 20260707_0016
Create Date: 2026-07-07 23:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260707_0017'
down_revision = '20260707_0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if 'task_types' in tables:
        columns = {column['name'] for column in inspector.get_columns('task_types')}
        if 'arm_mode' not in columns:
            op.add_column('task_types', sa.Column('arm_mode', sa.String(length=32), nullable=False, server_default='both_arms'))
        bind.execute(sa.text("UPDATE task_types SET arm_mode = 'both_arms' WHERE arm_mode IS NULL OR arm_mode = ''"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if 'task_types' in tables:
        columns = {column['name'] for column in inspector.get_columns('task_types')}
        if 'arm_mode' in columns:
            op.drop_column('task_types', 'arm_mode')
