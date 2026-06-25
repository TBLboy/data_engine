"""add updated_at to qc_tasks

Revision ID: 20260625_0006
Revises: 20260624_0005_dispatch_generation
Create Date: 2026-06-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260625_0006'
down_revision: Union[str, None] = '20260624_0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('qc_tasks', sa.Column('updated_at', sa.DateTime(timezone=False), nullable=True))
    op.execute("UPDATE qc_tasks SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('qc_tasks', 'updated_at', nullable=False)


def downgrade() -> None:
    op.drop_column('qc_tasks', 'updated_at')
