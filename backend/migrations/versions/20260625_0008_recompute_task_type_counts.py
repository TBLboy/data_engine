"""recompute task_type batch/episode counts with active-list 口径

Revision ID: 20260625_0008
Revises: 20260625_0007
Create Date: 2026-06-25

The old _refresh_task_type_stats counted batches/episodes with a bare
Batch.is_active filter, which included residual batches that have no active
ListRecord (e.g. the historical raw_data scan-artifact batch). That made
task-type totals (notably 待分类) disagree with the database/list views.
Recompute every task_type's stored totals using the authoritative口径:
only batches that join an active ListRecord in `lists`.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '20260625_0008'
down_revision: Union[str, None] = '20260625_0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE task_types SET
          total_batches = (
            SELECT count(*) FROM batches b
            JOIN lists l ON b.id = 'batch_' || substr(l.id, 6)
            WHERE l.is_active AND b.is_active AND b.task_type_id = task_types.id
          ),
          total_episodes = (
            SELECT count(*) FROM episodes e
            JOIN batches b ON e.batch_id = b.id
            JOIN lists l ON b.id = 'batch_' || substr(l.id, 6)
            WHERE l.is_active AND b.is_active AND b.task_type_id = task_types.id
          )
        """
    )


def downgrade() -> None:
    # Recompute is not reversible.
    pass
