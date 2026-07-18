"""data assets route c rollout

Revision ID: 20260715_0023
Revises: 20260710_0022
Create Date: 2026-07-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260715_0023'
down_revision = '20260710_0022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('batches', sa.Column('list_id', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_batches_list_id'), 'batches', ['list_id'], unique=False)
    with op.batch_alter_table('batches') as batch_op:
        batch_op.create_foreign_key('fk_batches_list_id_lists', 'lists', ['list_id'], ['id'])

    op.create_table(
        'batch_asset_rollups',
        sa.Column('batch_id', sa.String(length=64), nullable=False),
        sa.Column('episode_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_duration_sec', sa.Float(), nullable=False, server_default='0'),
        sa.Column('duration_covered_episode_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duration_missing_episode_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_frame_count', sa.BIGINT(), nullable=False, server_default='0'),
        sa.Column('frame_covered_episode_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('frame_missing_episode_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sampled_episode_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reviewed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('manual_pass_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('manual_fail_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('qualified_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unqualified_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pending_dataset_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_episode_updated_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('source_watermark', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('calculation_version', sa.String(length=64), nullable=False, server_default='batch-asset-rollup-v1'),
        sa.Column('refreshed_at', sa.DateTime(timezone=False), nullable=False),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id']),
        sa.PrimaryKeyConstraint('batch_id'),
    )

    op.create_table(
        'batch_asset_recompute_jobs',
        sa.Column('batch_id', sa.String(length=64), nullable=False),
        sa.Column('reason', sa.String(length=64), nullable=False, server_default='unknown'),
        sa.Column('requested_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('last_started_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('last_finished_at', sa.DateTime(timezone=False), nullable=True),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id']),
        sa.PrimaryKeyConstraint('batch_id'),
    )
    op.create_index(op.f('ix_batch_asset_recompute_jobs_status'), 'batch_asset_recompute_jobs', ['status'], unique=False)

    op.execute(
        """
        UPDATE batches
        SET list_id = (
            SELECT l.id
            FROM lists AS l
            WHERE batches.id = ('batch_' || substr(l.id, 6))
        )
        WHERE list_id IS NULL
          AND EXISTS (
            SELECT 1
            FROM lists AS l
            WHERE batches.id = ('batch_' || substr(l.id, 6))
          )
        """
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_batch_asset_recompute_jobs_status'), table_name='batch_asset_recompute_jobs')
    op.drop_table('batch_asset_recompute_jobs')
    op.drop_table('batch_asset_rollups')
    with op.batch_alter_table('batches') as batch_op:
        batch_op.drop_constraint('fk_batches_list_id_lists', type_='foreignkey')
    op.drop_index(op.f('ix_batches_list_id'), table_name='batches')
    op.drop_column('batches', 'list_id')
