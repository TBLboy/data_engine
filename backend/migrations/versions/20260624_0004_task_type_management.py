"""task type management and batch activation

Revision ID: 20260624_0004
Revises: 20260623_0003
Create Date: 2026-06-24 13:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260624_0004'
down_revision = '20260623_0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if 'task_types' in tables:
        task_type_columns = {column['name'] for column in inspector.get_columns('task_types')}
        if 'is_active' not in task_type_columns:
            op.add_column('task_types', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
        bind.execute(sa.text("UPDATE task_types SET is_active = TRUE WHERE is_active IS NULL"))

    if 'batches' in tables:
        batch_columns = {column['name'] for column in inspector.get_columns('batches')}
        if 'is_active' not in batch_columns:
            op.add_column('batches', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
        bind.execute(sa.text("UPDATE batches SET is_active = TRUE WHERE is_active IS NULL"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if 'batches' in tables:
        batch_columns = {column['name'] for column in inspector.get_columns('batches')}
        if 'is_active' in batch_columns:
            op.drop_column('batches', 'is_active')

    if 'task_types' in tables:
        task_type_columns = {column['name'] for column in inspector.get_columns('task_types')}
        if 'is_active' in task_type_columns:
            op.drop_column('task_types', 'is_active')
