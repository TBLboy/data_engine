"""add annotation eligibility projection counts

Revision ID: 20260720_0030
Revises: 20260720_0029
Create Date: 2026-07-20 13:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260720_0030'
down_revision = '20260720_0029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('task_annotation_rollups', sa.Column(
        'eligible_episode_count', sa.Integer(), nullable=False, server_default='0'
    ))
    op.add_column('task_annotation_rollups', sa.Column(
        'unannotated_count', sa.Integer(), nullable=False, server_default='0'
    ))
    # Existing rollup rows were created before eligibility became persistent.
    # Update them and add rows for active TaskTypes that have no task yet.
    op.execute("""
        INSERT INTO task_annotation_rollups (
            task_type_id, eligible_episode_count, unannotated_count,
            total_count, pending_count, assigned_count, in_progress_count,
            completed_count, invalidated_count, source_task_count,
            calculation_version, refreshed_at
        )
        SELECT
            active_scope.task_type_id,
            COUNT(active_scope.episode_id),
            SUM(CASE WHEN annotation_tasks.id IS NULL THEN 1 ELSE 0 END),
            0, 0, 0, 0, 0, 0, 0,
            'task-annotation-rollup-v1', CURRENT_TIMESTAMP
        FROM (
            SELECT batches.task_type_id, episodes.id AS episode_id
            FROM episodes
            JOIN batches ON episodes.batch_id = batches.id
            JOIN lists ON batches.list_id = lists.id
            WHERE episodes.final_dataset_status = 'QUALIFIED'
              AND episodes.is_active = true
              AND batches.is_active = true
              AND batches.list_id IS NOT NULL
              AND lists.is_active = true
        ) AS active_scope
        LEFT JOIN annotation_tasks ON annotation_tasks.episode_id = active_scope.episode_id
        GROUP BY active_scope.task_type_id
        ON CONFLICT (task_type_id) DO UPDATE SET
            eligible_episode_count = EXCLUDED.eligible_episode_count,
            unannotated_count = EXCLUDED.unannotated_count,
            refreshed_at = EXCLUDED.refreshed_at
    """)


def downgrade() -> None:
    op.drop_column('task_annotation_rollups', 'unannotated_count')
    op.drop_column('task_annotation_rollups', 'eligible_episode_count')
