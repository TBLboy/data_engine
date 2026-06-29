"""batch adjudication fields + batch_decision_log

Revision ID: 20260629_0012
Revises: 20260629_0011
Create Date: 2026-06-29 03:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '20260629_0012'
down_revision = '20260629_0011'
branch_labels = None
depends_on = None


def upgrade():
    # ── Batch 表新增字段 ──
    op.add_column('batches', sa.Column('manual_pass_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('batches', sa.Column('manual_fail_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('batches', sa.Column('failure_rate', sa.Float(), nullable=True))
    op.add_column('batches', sa.Column('reject_threshold', sa.Float(), nullable=False, server_default='0.10'))
    op.add_column('batches', sa.Column('failure_rate_denominator', sa.String(32), nullable=False, server_default='SAMPLED_COUNT'))
    op.add_column('batches', sa.Column('batch_decision', sa.String(32), nullable=False, server_default='PENDING'))
    op.add_column('batches', sa.Column('batch_decision_reason', sa.Text(), nullable=False, server_default=''))
    op.add_column('batches', sa.Column('decision_policy_version', sa.String(64), nullable=False, server_default='batch-reject-v1'))
    op.add_column('batches', sa.Column('adjudicated_at', sa.DateTime(timezone=False), nullable=True))

    # ── Episode 表新增字段 ──
    op.add_column('episodes', sa.Column('manual_qc_status', sa.String(32), nullable=False, server_default='NOT_REVIEWED'))
    op.add_column('episodes', sa.Column('manual_qc_result_id', sa.String(64), nullable=True))
    op.add_column('episodes', sa.Column('final_dataset_status', sa.String(32), nullable=False, server_default='PENDING'))
    op.add_column('episodes', sa.Column('final_decision_source', sa.String(64), nullable=False, server_default='PENDING_NOT_ADJUDICATED'))
    op.add_column('episodes', sa.Column('final_decision_reason', sa.Text(), nullable=False, server_default=''))
    op.add_column('episodes', sa.Column('final_decided_at', sa.DateTime(timezone=False), nullable=True))
    op.add_column('episodes', sa.Column('is_exportable', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('episodes', sa.Column('final_decision_policy_version', sa.String(64), nullable=False, server_default=''))
    op.add_column('episodes', sa.Column('batch_decision_log_id', sa.Integer(), nullable=True))

    # ── Batch Decision Log 审计表 ──
    op.create_table(
        'batch_decision_log',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('batch_id', sa.String(64), sa.ForeignKey('batches.id'), nullable=False, index=True),
        sa.Column('policy_version', sa.String(64), nullable=False, server_default='batch-reject-v1'),
        sa.Column('reject_threshold', sa.Float(), nullable=False),
        sa.Column('failure_rate_denominator', sa.String(32), nullable=False),
        sa.Column('total_episode_count', sa.Integer(), nullable=False),
        sa.Column('sampled_episode_count', sa.Integer(), nullable=False),
        sa.Column('reviewed_episode_count', sa.Integer(), nullable=False),
        sa.Column('manual_pass_count', sa.Integer(), nullable=False),
        sa.Column('manual_fail_count', sa.Integer(), nullable=False),
        sa.Column('failure_rate', sa.Float(), nullable=False),
        sa.Column('batch_decision', sa.String(32), nullable=False),
        sa.Column('decision_reason', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_by', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table('batch_decision_log')
    op.drop_column('episodes', 'batch_decision_log_id')
    op.drop_column('episodes', 'final_decision_policy_version')
    op.drop_column('episodes', 'is_exportable')
    op.drop_column('episodes', 'final_decided_at')
    op.drop_column('episodes', 'final_decision_reason')
    op.drop_column('episodes', 'final_decision_source')
    op.drop_column('episodes', 'final_dataset_status')
    op.drop_column('episodes', 'manual_qc_result_id')
    op.drop_column('episodes', 'manual_qc_status')
    op.drop_column('batches', 'adjudicated_at')
    op.drop_column('batches', 'decision_policy_version')
    op.drop_column('batches', 'batch_decision_reason')
    op.drop_column('batches', 'batch_decision')
    op.drop_column('batches', 'failure_rate_denominator')
    op.drop_column('batches', 'reject_threshold')
    op.drop_column('batches', 'failure_rate')
    op.drop_column('batches', 'manual_fail_count')
    op.drop_column('batches', 'manual_pass_count')
