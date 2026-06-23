"""minio control plane schema

Revision ID: 20260623_0002
Revises: 20260623_0001
Create Date: 2026-06-23 00:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260623_0002'
down_revision = '20260623_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'scan_jobs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('bucket', sa.String(length=128), nullable=False),
        sa.Column('scope', sa.String(length=32), nullable=False, server_default='full'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='running'),
        sa.Column('total_prefixes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('confirmed_lists', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_episodes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('new_episodes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('triggered_by', sa.String(length=64), nullable=False),
        sa.Column('error_detail', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_scan_jobs_bucket_started_at', 'scan_jobs', ['bucket', 'started_at'], unique=False)

    op.create_table(
        'classification_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pattern', sa.String(length=256), nullable=False),
        sa.Column('target_task_type_id', sa.String(length=64), nullable=False),
        sa.Column('candidate_label', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('match_scope', sa.String(length=32), nullable=False, server_default='basename'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_authoritative', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['target_task_type_id'], ['task_types.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_classification_rules_is_active'), 'classification_rules', ['is_active'], unique=False)
    op.create_index(op.f('ix_classification_rules_priority'), 'classification_rules', ['priority'], unique=False)

    op.create_table(
        'discovered_prefixes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('scan_job_id', sa.String(length=64), nullable=False),
        sa.Column('bucket', sa.String(length=128), nullable=False),
        sa.Column('prefix', sa.String(length=1024), nullable=False),
        sa.Column('depth', sa.Integer(), nullable=False),
        sa.Column('has_raw_child', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('has_processed_child', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('has_episode_grandchild', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_list_candidate', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('first_seen_scan_id', sa.String(length=64), nullable=True),
        sa.Column('last_seen_scan_id', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['first_seen_scan_id'], ['scan_jobs.id']),
        sa.ForeignKeyConstraint(['last_seen_scan_id'], ['scan_jobs.id']),
        sa.ForeignKeyConstraint(['scan_job_id'], ['scan_jobs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bucket', 'prefix', name='uq_discovered_prefixes_bucket_prefix'),
    )
    op.create_index(op.f('ix_discovered_prefixes_scan_job_id'), 'discovered_prefixes', ['scan_job_id'], unique=False)

    op.create_table(
        'lists',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('bucket', sa.String(length=128), nullable=False),
        sa.Column('list_prefix', sa.String(length=1024), nullable=False),
        sa.Column('confirmed_scan_id', sa.String(length=64), nullable=False),
        sa.Column('last_active_scan_id', sa.String(length=64), nullable=False),
        sa.Column('has_raw', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('has_processed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('total_raw_episodes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_processed_episodes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('candidate_task_type', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('candidate_source', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('final_task_type_id', sa.String(length=64), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['confirmed_scan_id'], ['scan_jobs.id']),
        sa.ForeignKeyConstraint(['final_task_type_id'], ['task_types.id']),
        sa.ForeignKeyConstraint(['last_active_scan_id'], ['scan_jobs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bucket', 'list_prefix', name='uq_lists_bucket_list_prefix'),
    )
    op.create_index(op.f('ix_lists_final_task_type_id'), 'lists', ['final_task_type_id'], unique=False)
    op.create_index(op.f('ix_lists_is_active'), 'lists', ['is_active'], unique=False)

    op.create_table(
        'episode_inventory',
        sa.Column('id', sa.String(length=128), nullable=False),
        sa.Column('list_id', sa.String(length=64), nullable=False),
        sa.Column('episode_name', sa.String(length=64), nullable=False),
        sa.Column('episode_prefix', sa.String(length=1024), nullable=False),
        sa.Column('raw_prefix', sa.String(length=1024), nullable=False, server_default=''),
        sa.Column('processed_prefix', sa.String(length=1024), nullable=False, server_default=''),
        sa.Column('state', sa.String(length=32), nullable=False, server_default='ingestable'),
        sa.Column('raw_exists', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('processed_exists', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('manifest_hash', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('metadata_hash', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('episode_id_from_manifest', sa.String(length=128), nullable=False, server_default=''),
        sa.Column('duration_sec', sa.Float(), nullable=False, server_default='0'),
        sa.Column('frame_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('state_changed_at', sa.DateTime(), nullable=True),
        sa.Column('first_seen_scan_id', sa.String(length=64), nullable=False),
        sa.Column('last_seen_scan_id', sa.String(length=64), nullable=False),
        sa.Column('ingested_episode_id', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['first_seen_scan_id'], ['scan_jobs.id']),
        sa.ForeignKeyConstraint(['ingested_episode_id'], ['episodes.id']),
        sa.ForeignKeyConstraint(['last_seen_scan_id'], ['scan_jobs.id']),
        sa.ForeignKeyConstraint(['list_id'], ['lists.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('list_id', 'episode_name', name='uq_episode_inventory_list_episode_name'),
    )
    op.create_index(op.f('ix_episode_inventory_ingested_episode_id'), 'episode_inventory', ['ingested_episode_id'], unique=False)
    op.create_index(op.f('ix_episode_inventory_list_id'), 'episode_inventory', ['list_id'], unique=False)
    op.create_index(op.f('ix_episode_inventory_state'), 'episode_inventory', ['state'], unique=False)

    op.create_table(
        'episode_objects',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('episode_inventory_id', sa.String(length=128), nullable=False),
        sa.Column('object_key', sa.String(length=1024), nullable=False),
        sa.Column('object_scope', sa.String(length=16), nullable=False),
        sa.Column('object_role', sa.String(length=64), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('content_hash', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('last_modified', sa.DateTime(), nullable=True),
        sa.Column('last_seen_scan_id', sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(['episode_inventory_id'], ['episode_inventory.id']),
        sa.ForeignKeyConstraint(['last_seen_scan_id'], ['scan_jobs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('episode_inventory_id', 'object_key', name='uq_episode_objects_episode_object_key'),
    )
    op.create_index(op.f('ix_episode_objects_content_hash'), 'episode_objects', ['content_hash'], unique=False)
    op.create_index(op.f('ix_episode_objects_episode_inventory_id'), 'episode_objects', ['episode_inventory_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_episode_objects_episode_inventory_id'), table_name='episode_objects')
    op.drop_index(op.f('ix_episode_objects_content_hash'), table_name='episode_objects')
    op.drop_table('episode_objects')
    op.drop_index(op.f('ix_episode_inventory_state'), table_name='episode_inventory')
    op.drop_index(op.f('ix_episode_inventory_list_id'), table_name='episode_inventory')
    op.drop_index(op.f('ix_episode_inventory_ingested_episode_id'), table_name='episode_inventory')
    op.drop_table('episode_inventory')
    op.drop_index(op.f('ix_lists_is_active'), table_name='lists')
    op.drop_index(op.f('ix_lists_final_task_type_id'), table_name='lists')
    op.drop_table('lists')
    op.drop_index(op.f('ix_discovered_prefixes_scan_job_id'), table_name='discovered_prefixes')
    op.drop_table('discovered_prefixes')
    op.drop_index(op.f('ix_classification_rules_priority'), table_name='classification_rules')
    op.drop_index(op.f('ix_classification_rules_is_active'), table_name='classification_rules')
    op.drop_table('classification_rules')
    op.drop_index('ix_scan_jobs_bucket_started_at', table_name='scan_jobs')
    op.drop_table('scan_jobs')
