"""scan ingestion v3 control plane

Revision ID: 20260717_0026
Revises: 20260716_0025
Create Date: 2026-07-17 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '20260717_0026'
down_revision = '20260716_0025'
branch_labels = None
depends_on = None


SCAN_ID = sa.BigInteger().with_variant(sa.Integer(), 'sqlite')


def _source_columns(table_name: str) -> None:
    op.add_column(table_name, sa.Column('source_status', sa.String(length=32), nullable=False, server_default='present'))
    op.add_column(table_name, sa.Column('missing_streak', sa.Integer(), nullable=False, server_default='0'))
    op.add_column(table_name, sa.Column('missing_evidence_shard_id', sa.BIGINT(), nullable=True))
    op.add_column(table_name, sa.Column('first_missing_at', sa.DateTime(timezone=False), nullable=True))
    op.add_column(table_name, sa.Column('last_missing_at', sa.DateTime(timezone=False), nullable=True))
    op.add_column(table_name, sa.Column('last_confirmed_present_at', sa.DateTime(timezone=False), nullable=True))
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.create_foreign_key(
            f'fk_{table_name}_missing_evidence_shard', 'scan_shards',
            ['missing_evidence_shard_id'], ['id'],
        )
    op.create_index(op.f(f'ix_{table_name}_source_status'), table_name, ['source_status'], unique=False)


def _drop_source_columns(table_name: str) -> None:
    op.drop_index(op.f(f'ix_{table_name}_source_status'), table_name=table_name)
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_constraint(f'fk_{table_name}_missing_evidence_shard', type_='foreignkey')
        for name in (
            'last_confirmed_present_at', 'last_missing_at', 'first_missing_at',
            'missing_evidence_shard_id', 'missing_streak', 'source_status',
        ):
            batch_op.drop_column(name)


def upgrade() -> None:
    op.add_column('scan_jobs', sa.Column('scan_mode', sa.String(length=32), nullable=False, server_default='full'))
    op.add_column('scan_jobs', sa.Column('priority', sa.Integer(), nullable=False, server_default='100'))
    op.add_column('scan_jobs', sa.Column('trigger_source', sa.String(length=32), nullable=False, server_default='manual'))
    op.add_column('scan_jobs', sa.Column('active_key', sa.String(length=256), nullable=True))
    for name in ('total_shards', 'succeeded_shards', 'failed_shards', 'running_shards', 'skipped_shards'):
        op.add_column('scan_jobs', sa.Column(name, sa.Integer(), nullable=False, server_default='0'))
    op.add_column('scan_jobs', sa.Column('heartbeat_at', sa.DateTime(timezone=False), nullable=True))
    op.add_column('scan_jobs', sa.Column('cancel_requested_at', sa.DateTime(timezone=False), nullable=True))
    op.add_column('scan_jobs', sa.Column('error_summary', sa.Text(), nullable=False, server_default=''))
    op.add_column('scan_jobs', sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()))
    op.add_column('scan_jobs', sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()))
    op.create_index(op.f('ix_scan_jobs_scan_mode'), 'scan_jobs', ['scan_mode'], unique=False)
    op.create_index('uq_scan_jobs_active_key', 'scan_jobs', ['active_key'], unique=True)

    op.create_table(
        'scan_shards',
        sa.Column('id', SCAN_ID, autoincrement=True, nullable=False),
        sa.Column('scan_job_id', sa.String(length=64), nullable=False),
        sa.Column('parent_shard_id', SCAN_ID, nullable=True),
        sa.Column('shard_key', sa.String(length=1200), nullable=False),
        sa.Column('shard_type', sa.String(length=32), nullable=False),
        sa.Column('bucket', sa.String(length=128), nullable=False),
        sa.Column('prefix', sa.String(length=1024), nullable=False, server_default=''),
        sa.Column('range_start', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('range_end', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('attempt', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('lease_owner', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('lease_expires_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False, server_default='600'),
        sa.Column('next_retry_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('processed_objects', sa.BIGINT(), nullable=False, server_default='0'),
        sa.Column('total_objects', sa.BIGINT(), nullable=False, server_default='0'),
        sa.Column('processed_episodes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_episodes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('changed_episodes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('new_episodes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_detail', sa.Text(), nullable=False, server_default=''),
        sa.Column('started_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['parent_shard_id'], ['scan_shards.id']),
        sa.ForeignKeyConstraint(['scan_job_id'], ['scan_jobs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scan_job_id', 'shard_key', name='uq_scan_shards_job_key'),
    )
    op.create_index(op.f('ix_scan_shards_scan_job_id'), 'scan_shards', ['scan_job_id'], unique=False)
    op.create_index(op.f('ix_scan_shards_parent_shard_id'), 'scan_shards', ['parent_shard_id'], unique=False)
    op.create_index(op.f('ix_scan_shards_status'), 'scan_shards', ['status'], unique=False)
    op.create_index('ix_scan_shards_claim', 'scan_shards', ['status', 'next_retry_at', 'priority', 'id'], unique=False)

    op.create_table(
        'scan_prefix_states',
        sa.Column('id', SCAN_ID, autoincrement=True, nullable=False),
        sa.Column('bucket', sa.String(length=128), nullable=False),
        sa.Column('prefix', sa.String(length=1024), nullable=False),
        sa.Column('list_id', sa.String(length=64), nullable=True),
        sa.Column('scan_policy', sa.String(length=32), nullable=False, server_default='adaptive'),
        sa.Column('last_success_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('last_changed_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('next_scan_at', sa.DateTime(timezone=False), nullable=True),
        sa.Column('consecutive_unchanged', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_episode_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_object_count', sa.BIGINT(), nullable=False, server_default='0'),
        sa.Column('last_duration_seconds', sa.Float(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['list_id'], ['lists.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bucket', 'prefix', name='uq_scan_prefix_states_bucket_prefix'),
    )
    op.create_index(op.f('ix_scan_prefix_states_list_id'), 'scan_prefix_states', ['list_id'], unique=False)
    op.create_index('ix_scan_prefix_states_due', 'scan_prefix_states', ['scan_policy', 'next_scan_at'], unique=False)

    _source_columns('lists')
    _source_columns('episode_inventory')
    _source_columns('episode_objects')

    op.add_column('episode_inventory', sa.Column('max_observed_state', sa.String(length=32), nullable=False, server_default='ingestable'))
    op.add_column('episode_inventory', sa.Column('raw_source_status', sa.String(length=32), nullable=False, server_default='present'))
    op.add_column('episode_inventory', sa.Column('processed_source_status', sa.String(length=32), nullable=False, server_default='present'))
    op.add_column('episode_inventory', sa.Column('raw_missing_streak', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('episode_inventory', sa.Column('processed_missing_streak', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('episode_inventory', sa.Column('raw_missing_evidence_shard_id', sa.BIGINT(), nullable=True))
    op.add_column('episode_inventory', sa.Column('processed_missing_evidence_shard_id', sa.BIGINT(), nullable=True))
    op.add_column('episode_inventory', sa.Column('raw_first_missing_at', sa.DateTime(timezone=False), nullable=True))
    op.add_column('episode_inventory', sa.Column('processed_first_missing_at', sa.DateTime(timezone=False), nullable=True))
    op.add_column('episode_inventory', sa.Column('raw_last_missing_at', sa.DateTime(timezone=False), nullable=True))
    op.add_column('episode_inventory', sa.Column('processed_last_missing_at', sa.DateTime(timezone=False), nullable=True))
    with op.batch_alter_table('episode_inventory') as batch_op:
        batch_op.create_foreign_key(
            'fk_episode_inventory_raw_missing_evidence_shard', 'scan_shards',
            ['raw_missing_evidence_shard_id'], ['id'],
        )
        batch_op.create_foreign_key(
            'fk_episode_inventory_processed_missing_evidence_shard', 'scan_shards',
            ['processed_missing_evidence_shard_id'], ['id'],
        )
    for name in ('raw_object_count', 'processed_object_count', 'raw_total_size_bytes', 'processed_total_size_bytes'):
        op.add_column('episode_inventory', sa.Column(name, sa.BIGINT(), nullable=False, server_default='0'))
    op.add_column('episode_inventory', sa.Column('raw_content_fingerprint', sa.String(length=64), nullable=False, server_default=''))
    op.add_column('episode_inventory', sa.Column('processed_content_fingerprint', sa.String(length=64), nullable=False, server_default=''))
    op.add_column('episode_inventory', sa.Column('latest_object_modified_at', sa.DateTime(timezone=False), nullable=True))
    op.execute("UPDATE episode_inventory SET max_observed_state = state")

    op.add_column('episodes', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index(op.f('ix_episodes_is_active'), 'episodes', ['is_active'], unique=False)

    op.add_column('batch_asset_recompute_jobs', sa.Column('rerun_requested', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('task_asset_recompute_jobs', sa.Column('rerun_requested', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('task_asset_recompute_jobs', 'rerun_requested')
    op.drop_column('batch_asset_recompute_jobs', 'rerun_requested')
    op.drop_index(op.f('ix_episodes_is_active'), table_name='episodes')
    op.drop_column('episodes', 'is_active')

    with op.batch_alter_table('episode_inventory') as batch_op:
        batch_op.drop_constraint('fk_episode_inventory_processed_missing_evidence_shard', type_='foreignkey')
        batch_op.drop_constraint('fk_episode_inventory_raw_missing_evidence_shard', type_='foreignkey')
        for name in (
            'latest_object_modified_at', 'processed_content_fingerprint', 'raw_content_fingerprint',
            'processed_total_size_bytes', 'raw_total_size_bytes', 'processed_object_count', 'raw_object_count',
            'processed_last_missing_at', 'raw_last_missing_at',
            'processed_first_missing_at', 'raw_first_missing_at',
            'processed_missing_evidence_shard_id', 'raw_missing_evidence_shard_id',
            'processed_missing_streak', 'raw_missing_streak', 'processed_source_status', 'raw_source_status',
            'max_observed_state',
        ):
            batch_op.drop_column(name)
    _drop_source_columns('episode_objects')
    _drop_source_columns('episode_inventory')
    _drop_source_columns('lists')

    op.drop_index('ix_scan_prefix_states_due', table_name='scan_prefix_states')
    op.drop_index(op.f('ix_scan_prefix_states_list_id'), table_name='scan_prefix_states')
    op.drop_table('scan_prefix_states')
    op.drop_index('ix_scan_shards_claim', table_name='scan_shards')
    op.drop_index(op.f('ix_scan_shards_status'), table_name='scan_shards')
    op.drop_index(op.f('ix_scan_shards_parent_shard_id'), table_name='scan_shards')
    op.drop_index(op.f('ix_scan_shards_scan_job_id'), table_name='scan_shards')
    op.drop_table('scan_shards')

    op.drop_index('uq_scan_jobs_active_key', table_name='scan_jobs')
    op.drop_index(op.f('ix_scan_jobs_scan_mode'), table_name='scan_jobs')
    for name in (
        'updated_at', 'created_at', 'error_summary', 'cancel_requested_at', 'heartbeat_at',
        'skipped_shards', 'running_shards', 'failed_shards', 'succeeded_shards', 'total_shards',
        'active_key', 'trigger_source', 'priority', 'scan_mode',
    ):
        op.drop_column('scan_jobs', name)
