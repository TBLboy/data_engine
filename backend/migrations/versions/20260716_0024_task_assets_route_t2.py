"""task assets route t2 rollout

Revision ID: 20260716_0024
Revises: 20260715_0023
Create Date: 2026-07-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260716_0024'
down_revision = '20260715_0023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'task_asset_rollups',
        sa.Column('task_type_id', sa.String(length=64), nullable=False),
        sa.Column('batch_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('episode_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reviewed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('not_reviewed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('manual_pass_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('manual_fail_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('qualified_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unqualified_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pending_dataset_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_duration_sec', sa.Float(), nullable=False, server_default='0'),
        sa.Column('duration_covered_episode_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duration_missing_episode_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_frame_count', sa.BIGINT(), nullable=False, server_default='0'),
        sa.Column('frame_covered_episode_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('frame_missing_episode_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sampled_episode_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('accepted_batch_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rejected_batch_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pending_batch_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source_batch_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source_watermark', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('calculation_version', sa.String(length=64), nullable=False, server_default='task-asset-rollup-v1'),
        sa.Column('refreshed_at', sa.DateTime(timezone=False), nullable=False),
        sa.ForeignKeyConstraint(['task_type_id'], ['task_types.id']),
        sa.PrimaryKeyConstraint('task_type_id'),
    )
    op.create_index(op.f('ix_task_asset_rollups_refreshed_at'), 'task_asset_rollups', ['refreshed_at'], unique=False)

    op.create_table(
        'task_asset_recompute_jobs',
        sa.Column('task_type_id', sa.String(length=64), nullable=False),
        sa.Column('reason', sa.String(length=64), nullable=False, server_default='unknown'),
        sa.Column('requested_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('last_started_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('last_finished_at', sa.DateTime(timezone=False), nullable=True),
        sa.ForeignKeyConstraint(['task_type_id'], ['task_types.id']),
        sa.PrimaryKeyConstraint('task_type_id'),
    )
    op.create_index(op.f('ix_task_asset_recompute_jobs_status'), 'task_asset_recompute_jobs', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_task_asset_recompute_jobs_status'), table_name='task_asset_recompute_jobs')
    op.drop_table('task_asset_recompute_jobs')
    op.drop_index(op.f('ix_task_asset_rollups_refreshed_at'), table_name='task_asset_rollups')
    op.drop_table('task_asset_rollups')
