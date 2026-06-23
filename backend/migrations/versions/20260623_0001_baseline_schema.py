"""baseline schema

Revision ID: 20260623_0001
Revises:
Create Date: 2026-06-23 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260623_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('operator', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=128), nullable=False),
        sa.Column('target', sa.String(length=128), nullable=False),
        sa.Column('detail', sa.String(length=500), nullable=False),
        sa.Column('time', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'task_types',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('total_batches', sa.Integer(), nullable=False),
        sa.Column('total_episodes', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('avatar', sa.String(length=8), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Integer(), nullable=False),
        sa.Column('password_changed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table(
        'batches',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('task_type_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('imported_at', sa.DateTime(), nullable=False),
        sa.Column('episode_count', sa.Integer(), nullable=False),
        sa.Column('sampled_episode_count', sa.Integer(), nullable=False),
        sa.Column('completed_sample_count', sa.Integer(), nullable=False),
        sa.Column('dispatch_mode', sa.String(length=32), nullable=False),
        sa.Column('sampling_ratio', sa.Integer(), nullable=False),
        sa.Column('qc_status', sa.String(length=32), nullable=False),
        sa.Column('pass_rate', sa.Float(), nullable=False),
        sa.Column('top_reason', sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(['task_type_id'], ['task_types.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_batches_task_type_id'), 'batches', ['task_type_id'], unique=False)
    op.create_table(
        'episodes',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('batch_id', sa.String(length=64), nullable=False),
        sa.Column('task_name', sa.String(length=128), nullable=False),
        sa.Column('duration_sec', sa.Float(), nullable=False),
        sa.Column('frame_count', sa.Integer(), nullable=False),
        sa.Column('qc_status', sa.String(length=32), nullable=False),
        sa.Column('qc_result', sa.String(length=32), nullable=False),
        sa.Column('reviewer', sa.String(length=64), nullable=False),
        sa.Column('reason_code', sa.String(length=128), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('in_candidate_pool', sa.Integer(), nullable=False),
        sa.Column('sampled_for_qc', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_episodes_batch_id'), 'episodes', ['batch_id'], unique=False)
    op.create_table(
        'qc_review_revisions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('episode_id', sa.String(length=64), nullable=False),
        sa.Column('revision_no', sa.Integer(), nullable=False),
        sa.Column('result', sa.String(length=32), nullable=False),
        sa.Column('primary_reason', sa.String(length=128), nullable=False),
        sa.Column('operator', sa.String(length=64), nullable=False),
        sa.Column('note', sa.String(length=500), nullable=False),
        sa.Column('time', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['episode_id'], ['episodes.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_qc_review_revisions_episode_id'), 'qc_review_revisions', ['episode_id'], unique=False)
    op.create_table(
        'qc_tasks',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('episode_id', sa.String(length=64), nullable=False),
        sa.Column('batch_id', sa.String(length=64), nullable=False),
        sa.Column('batch_name', sa.String(length=128), nullable=False),
        sa.Column('task_name', sa.String(length=128), nullable=False),
        sa.Column('assignee', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('priority', sa.String(length=32), nullable=False),
        sa.Column('dispatch_mode', sa.String(length=32), nullable=False),
        sa.Column('sampling_ratio', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('lock_owner_user_id', sa.String(length=64), nullable=False),
        sa.Column('lock_owner_name', sa.String(length=64), nullable=False),
        sa.Column('lock_acquired_at', sa.DateTime(), nullable=True),
        sa.Column('lock_expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id']),
        sa.ForeignKeyConstraint(['episode_id'], ['episodes.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_qc_tasks_batch_id'), 'qc_tasks', ['batch_id'], unique=False)
    op.create_index(op.f('ix_qc_tasks_episode_id'), 'qc_tasks', ['episode_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_qc_tasks_episode_id'), table_name='qc_tasks')
    op.drop_index(op.f('ix_qc_tasks_batch_id'), table_name='qc_tasks')
    op.drop_table('qc_tasks')
    op.drop_index(op.f('ix_qc_review_revisions_episode_id'), table_name='qc_review_revisions')
    op.drop_table('qc_review_revisions')
    op.drop_index(op.f('ix_episodes_batch_id'), table_name='episodes')
    op.drop_table('episodes')
    op.drop_index(op.f('ix_batches_task_type_id'), table_name='batches')
    op.drop_table('batches')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_table('users')
    op.drop_table('task_types')
    op.drop_table('audit_events')
