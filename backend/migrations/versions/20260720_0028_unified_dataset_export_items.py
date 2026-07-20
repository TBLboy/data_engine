"""unified dataset export job metadata and per-episode snapshots

Revision ID: 20260720_0028
Revises: 20260718_0027
Create Date: 2026-07-20 10:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260720_0028'
down_revision = '20260718_0027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('dataset_export_jobs') as batch_op:
        batch_op.add_column(sa.Column('export_type', sa.String(length=32), nullable=False, server_default='qualified_dataset'))
        batch_op.add_column(sa.Column('annotation_completed_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('training_default_included_count', sa.Integer(), nullable=False, server_default='0'))

    op.create_table(
        'dataset_export_items',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('export_job_id', sa.Integer(), nullable=False),
        sa.Column('episode_id', sa.String(length=64), nullable=False),
        sa.Column('inclusion_status', sa.String(length=32), nullable=False, server_default='included'),
        sa.Column('episode_snapshot_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('annotation_completed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('annotation_status', sa.String(length=32), nullable=False, server_default='not_created'),
        sa.Column('training_default_included', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('annotation_task_id', sa.String(length=64), nullable=True),
        sa.Column('annotation_revision_id', sa.Integer(), nullable=True),
        sa.Column('revision_no', sa.Integer(), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('schema_id', sa.String(length=64), nullable=True),
        sa.Column('schema_version', sa.Integer(), nullable=True),
        sa.Column('schema_content_hash', sa.String(length=64), nullable=True),
        sa.Column('task_outcome', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['export_job_id'], ['dataset_export_jobs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_dataset_export_items_export_job_id'), 'dataset_export_items', ['export_job_id'], unique=False)
    op.create_index(op.f('ix_dataset_export_items_episode_id'), 'dataset_export_items', ['episode_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_dataset_export_items_episode_id'), table_name='dataset_export_items')
    op.drop_index(op.f('ix_dataset_export_items_export_job_id'), table_name='dataset_export_items')
    op.drop_table('dataset_export_items')
    with op.batch_alter_table('dataset_export_jobs') as batch_op:
        batch_op.drop_column('training_default_included_count')
        batch_op.drop_column('annotation_completed_count')
        batch_op.drop_column('export_type')
