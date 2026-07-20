"""add active annotation completion coverage

Revision ID: 20260720_0032
Revises: 20260720_0031
Create Date: 2026-07-20 15:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260720_0032'
down_revision = '20260720_0031'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('task_annotation_rollups', sa.Column(
        'active_completed_count', sa.Integer(), nullable=False, server_default='0'
    ))
    # Completion coverage is only meaningful inside the canonical export scope.
    # Historical completed tasks that have since been invalidated stay in the
    # status projection but must not increase active coverage.
    op.execute("""
        UPDATE task_annotation_rollups AS rollup
        SET active_completed_count = scoped.completed_count,
            refreshed_at = CURRENT_TIMESTAMP
        FROM (
            SELECT batches.task_type_id, COUNT(annotation_tasks.id) AS completed_count
            FROM episodes
            JOIN batches ON episodes.batch_id = batches.id
            JOIN lists ON batches.list_id = lists.id
            JOIN annotation_tasks ON annotation_tasks.episode_id = episodes.id
            WHERE episodes.final_dataset_status = 'QUALIFIED'
              AND episodes.is_active = true
              AND batches.is_active = true
              AND batches.list_id IS NOT NULL
              AND lists.is_active = true
              AND annotation_tasks.work_status = 'completed'
            GROUP BY batches.task_type_id
        ) AS scoped
        WHERE rollup.task_type_id = scoped.task_type_id
    """)


def downgrade() -> None:
    op.drop_column('task_annotation_rollups', 'active_completed_count')
