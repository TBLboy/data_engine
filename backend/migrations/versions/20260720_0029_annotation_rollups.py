"""persistent annotation operation rollups

Revision ID: 20260720_0029
Revises: 20260720_0028
Create Date: 2026-07-20 11:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260720_0029'
down_revision = '20260720_0028'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'task_annotation_rollups',
        sa.Column('task_type_id', sa.String(length=64), nullable=False),
        sa.Column('total_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pending_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('assigned_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('in_progress_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('invalidated_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source_task_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('calculation_version', sa.String(length=64), nullable=False, server_default='task-annotation-rollup-v1'),
        sa.Column('refreshed_at', sa.DateTime(timezone=False), nullable=False),
        sa.ForeignKeyConstraint(['task_type_id'], ['task_types.id']),
        sa.PrimaryKeyConstraint('task_type_id'),
    )
    op.create_index(
        op.f('ix_task_annotation_rollups_refreshed_at'),
        'task_annotation_rollups',
        ['refreshed_at'],
        unique=False,
    )

    op.create_table(
        'reviewer_annotation_rollups',
        sa.Column('task_type_id', sa.String(length=64), nullable=False),
        sa.Column('reviewer_id', sa.String(length=64), nullable=False),
        sa.Column('task_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('refreshed_at', sa.DateTime(timezone=False), nullable=False),
        sa.ForeignKeyConstraint(['task_type_id'], ['task_types.id']),
        sa.ForeignKeyConstraint(['reviewer_id'], ['users.id']),
        sa.PrimaryKeyConstraint('task_type_id', 'reviewer_id'),
    )
    op.create_index(
        op.f('ix_reviewer_annotation_rollups_reviewer_id'),
        'reviewer_annotation_rollups',
        ['reviewer_id'],
        unique=False,
    )
    # Existing production tasks predate this projection, so populate it before
    # the statistics endpoint starts reading rollups exclusively.
    op.execute("""
        INSERT INTO task_annotation_rollups (
            task_type_id, total_count, pending_count, assigned_count,
            in_progress_count, completed_count, invalidated_count,
            source_task_count, calculation_version, refreshed_at
        )
        SELECT
            task_type_id,
            COUNT(*),
            SUM(CASE WHEN work_status = 'pending' THEN 1 ELSE 0 END),
            SUM(CASE WHEN work_status = 'assigned' THEN 1 ELSE 0 END),
            SUM(CASE WHEN work_status = 'in_progress' THEN 1 ELSE 0 END),
            SUM(CASE WHEN work_status = 'completed' THEN 1 ELSE 0 END),
            SUM(CASE WHEN work_status = 'invalidated' THEN 1 ELSE 0 END),
            COUNT(*),
            'task-annotation-rollup-v1',
            CURRENT_TIMESTAMP
        FROM annotation_tasks
        GROUP BY task_type_id
    """)
    op.execute("""
        INSERT INTO reviewer_annotation_rollups (
            task_type_id, reviewer_id, task_count, refreshed_at
        )
        SELECT task_type_id, assigned_to, COUNT(*), CURRENT_TIMESTAMP
        FROM annotation_tasks
        WHERE assigned_to IS NOT NULL
        GROUP BY task_type_id, assigned_to
    """)


def downgrade() -> None:
    op.drop_index(op.f('ix_reviewer_annotation_rollups_reviewer_id'), table_name='reviewer_annotation_rollups')
    op.drop_table('reviewer_annotation_rollups')
    op.drop_index(op.f('ix_task_annotation_rollups_refreshed_at'), table_name='task_annotation_rollups')
    op.drop_table('task_annotation_rollups')
