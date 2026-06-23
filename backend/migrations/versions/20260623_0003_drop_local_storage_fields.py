"""drop local storage fields and legacy ingest jobs

Revision ID: 20260623_0003
Revises: 20260623_0002
Create Date: 2026-06-23 01:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260623_0003'
down_revision = '20260623_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if 'ingest_jobs' in tables:
        op.drop_table('ingest_jobs')
    if 'batches' in tables:
        batch_columns = {column['name'] for column in inspector.get_columns('batches')}
        if 'storage_path' in batch_columns:
            op.drop_column('batches', 'storage_path')
    if 'episodes' in tables:
        episode_columns = {column['name'] for column in inspector.get_columns('episodes')}
        episode_indexes = {item['name'] for item in inspector.get_indexes('episodes')}
        if 'ix_episodes_source_hash' in episode_indexes:
            op.drop_index('ix_episodes_source_hash', table_name='episodes')
        if 'source_hash' in episode_columns:
            op.drop_column('episodes', 'source_hash')
        if 'source_path' in episode_columns:
            op.drop_column('episodes', 'source_path')
        if 'ingest_status' in episode_columns:
            op.drop_column('episodes', 'ingest_status')


def downgrade() -> None:
    op.add_column('episodes', sa.Column('ingest_status', sa.String(length=32), nullable=False, server_default='indexed'))
    op.add_column('episodes', sa.Column('source_path', sa.String(length=255), nullable=False, server_default=''))
    op.add_column('episodes', sa.Column('source_hash', sa.String(length=64), nullable=False, server_default=''))
    op.create_index('ix_episodes_source_hash', 'episodes', ['source_hash'], unique=False)
    op.add_column('batches', sa.Column('storage_path', sa.String(length=255), nullable=False, server_default=''))
    op.create_table(
        'ingest_jobs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('batch_id', sa.String(length=64), nullable=False),
        sa.Column('batch_name', sa.String(length=128), nullable=False),
        sa.Column('source_path', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('episodes', sa.Integer(), nullable=False),
        sa.Column('imported_episodes', sa.Integer(), nullable=False),
        sa.Column('skipped_episodes', sa.Integer(), nullable=False),
        sa.Column('detail', sa.String(length=500), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ingest_jobs_batch_id'), 'ingest_jobs', ['batch_id'], unique=False)
