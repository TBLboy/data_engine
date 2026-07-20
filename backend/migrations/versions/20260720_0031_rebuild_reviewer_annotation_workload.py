"""rebuild reviewer annotation workload projection

Revision ID: 20260720_0031
Revises: 20260720_0030
Create Date: 2026-07-20 14:00:00.000000
"""

from alembic import op


revision = '20260720_0031'
down_revision = '20260720_0030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Reviewer workload represents actionable current ownership, not completed
    # assignment history. Existing rows from the initial rollup migration must
    # therefore be rebuilt with the same predicate as the service projection.
    op.execute('DELETE FROM reviewer_annotation_rollups')
    op.execute("""
        INSERT INTO reviewer_annotation_rollups (
            task_type_id, reviewer_id, task_count, refreshed_at
        )
        SELECT task_type_id, assigned_to, COUNT(*), CURRENT_TIMESTAMP
        FROM annotation_tasks
        WHERE assigned_to IS NOT NULL
          AND work_status IN ('assigned', 'in_progress')
        GROUP BY task_type_id, assigned_to
    """)


def downgrade() -> None:
    # The preceding migration's historical backfill is not reconstructable on
    # downgrade; the current-workload projection remains valid.
    pass
