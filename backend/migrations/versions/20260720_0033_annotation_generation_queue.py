"""persistent annotation generation queue and AI run audit

Revision ID: 20260720_0033
Revises: 20260720_0032
Create Date: 2026-07-20 16:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260720_0033'
down_revision = '20260720_0032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'annotation_generation_jobs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('annotation_task_id', sa.String(length=64), nullable=False),
        sa.Column('request_group_id', sa.String(length=128), nullable=True),
        sa.Column('job_type', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='queued'),
        sa.Column('requested_draft_version', sa.Integer(), nullable=True),
        sa.Column('task_description_snapshot', sa.Text(), nullable=False, server_default=''),
        sa.Column('sub_goal_schema_id', sa.String(length=64), nullable=False),
        sa.Column('sub_goal_schema_version', sa.Integer(), nullable=False),
        sa.Column('sub_goal_schema_content_hash', sa.String(length=64), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('lease_owner', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('lease_expires_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('requested_by', sa.String(length=64), nullable=True),
        sa.Column('cancel_requested_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('error_detail', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=False), nullable=True),
        sa.ForeignKeyConstraint(['annotation_task_id'], ['annotation_tasks.id']),
        sa.ForeignKeyConstraint(['sub_goal_schema_id'], ['sub_goal_schemas.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_annotation_generation_jobs_claim',
        'annotation_generation_jobs',
        ['status', 'next_retry_at', 'priority', 'id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_annotation_generation_jobs_task_id'),
        'annotation_generation_jobs',
        ['annotation_task_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_annotation_generation_jobs_request_group'),
        'annotation_generation_jobs',
        ['request_group_id'],
        unique=False,
    )
    op.create_index(
        'ix_annotation_generation_jobs_task_mutating',
        'annotation_generation_jobs',
        ['annotation_task_id', 'status'],
        unique=False,
        postgresql_where=sa.text(
            "job_type IN ('initial','all','instruction','variants','sub_goals') "
            "AND status IN ('queued','running')"
        ),
    )

    op.create_table(
        'annotation_ai_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('annotation_task_id', sa.String(length=64), nullable=False),
        sa.Column('annotation_generation_job_id', sa.String(length=64), nullable=False),
        sa.Column('attempt_no', sa.Integer(), nullable=False),
        sa.Column('model_name', sa.String(length=128), nullable=False),
        sa.Column('prompt_version', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('frame_sampler_version', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('input_summary_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('raw_response_text', sa.Text(), nullable=False, server_default=''),
        sa.Column('parsed_response_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('run_status', sa.String(length=32), nullable=False, server_default='running'),
        sa.Column('error_detail', sa.Text(), nullable=False, server_default=''),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=False), nullable=True),
        sa.ForeignKeyConstraint(['annotation_task_id'], ['annotation_tasks.id']),
        sa.ForeignKeyConstraint(['annotation_generation_job_id'], ['annotation_generation_jobs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_annotation_ai_runs_generation_job_id'),
        'annotation_ai_runs',
        ['annotation_generation_job_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_annotation_ai_runs_task_id'),
        'annotation_ai_runs',
        ['annotation_task_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_annotation_ai_runs_task_id'), table_name='annotation_ai_runs')
    op.drop_index(op.f('ix_annotation_ai_runs_generation_job_id'), table_name='annotation_ai_runs')
    op.drop_table('annotation_ai_runs')
    op.drop_index('ix_annotation_generation_jobs_task_mutating', table_name='annotation_generation_jobs')
    op.drop_index(op.f('ix_annotation_generation_jobs_request_group'), table_name='annotation_generation_jobs')
    op.drop_index(op.f('ix_annotation_generation_jobs_task_id'), table_name='annotation_generation_jobs')
    op.drop_index('ix_annotation_generation_jobs_claim', table_name='annotation_generation_jobs')
    op.drop_table('annotation_generation_jobs')
