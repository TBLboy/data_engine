from datetime import datetime

from sqlalchemy import BIGINT, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


SCAN_BIGINT = BIGINT().with_variant(Integer, 'sqlite')


class ScanJob(Base):
    __tablename__ = 'scan_jobs'
    __table_args__ = (Index('ix_scan_jobs_bucket_started_at', 'bucket', 'started_at'),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), default='full', nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='running', nullable=False)
    total_prefixes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confirmed_lists: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_episodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_episodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(64), nullable=False)
    error_detail: Mapped[str] = mapped_column(String(500), default='', nullable=False)
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    scan_mode: Mapped[str] = mapped_column(String(32), default='full', nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    trigger_source: Mapped[str] = mapped_column(String(32), default='manual', nullable=False)
    active_key: Mapped[str | None] = mapped_column(String(256), nullable=True, unique=True)
    total_shards: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    succeeded_shards: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_shards: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    running_shards: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_shards: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    heartbeat_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    cancel_requested_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    error_summary: Mapped[str] = mapped_column(Text, default='', nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)


class ScanShard(Base):
    __tablename__ = 'scan_shards'
    __table_args__ = (
        UniqueConstraint('scan_job_id', 'shard_key', name='uq_scan_shards_job_key'),
        Index('ix_scan_shards_claim', 'status', 'next_retry_at', 'priority', 'id'),
    )

    id: Mapped[int] = mapped_column(SCAN_BIGINT, primary_key=True, autoincrement=True)
    scan_job_id: Mapped[str] = mapped_column(ForeignKey('scan_jobs.id'), nullable=False, index=True)
    parent_shard_id: Mapped[int | None] = mapped_column(ForeignKey('scan_shards.id'), nullable=True, index=True)
    shard_key: Mapped[str] = mapped_column(String(1200), nullable=False)
    shard_type: Mapped[str] = mapped_column(String(32), nullable=False)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    prefix: Mapped[str] = mapped_column(String(1024), default='', nullable=False)
    range_start: Mapped[str] = mapped_column(String(128), default='', nullable=False)
    range_end: Mapped[str] = mapped_column(String(128), default='', nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='pending', nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    lease_owner: Mapped[str] = mapped_column(String(128), default='', nullable=False)
    lease_expires_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    heartbeat_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    next_retry_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    processed_objects: Mapped[int] = mapped_column(SCAN_BIGINT, default=0, nullable=False)
    total_objects: Mapped[int] = mapped_column(SCAN_BIGINT, default=0, nullable=False)
    processed_episodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_episodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    changed_episodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_episodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_detail: Mapped[str] = mapped_column(Text, default='', nullable=False)
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)


class ScanPrefixState(Base):
    __tablename__ = 'scan_prefix_states'
    __table_args__ = (
        UniqueConstraint('bucket', 'prefix', name='uq_scan_prefix_states_bucket_prefix'),
        Index('ix_scan_prefix_states_due', 'scan_policy', 'next_scan_at'),
    )

    id: Mapped[int] = mapped_column(SCAN_BIGINT, primary_key=True, autoincrement=True)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    prefix: Mapped[str] = mapped_column(String(1024), nullable=False)
    list_id: Mapped[str | None] = mapped_column(ForeignKey('lists.id'), nullable=True, index=True)
    scan_policy: Mapped[str] = mapped_column(String(32), default='adaptive', nullable=False)
    last_success_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_changed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    next_scan_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    consecutive_unchanged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_object_count: Mapped[int] = mapped_column(SCAN_BIGINT, default=0, nullable=False)
    last_duration_seconds: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default='', nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)


class DiscoveredPrefix(Base):
    __tablename__ = 'discovered_prefixes'
    __table_args__ = (UniqueConstraint('bucket', 'prefix', name='uq_discovered_prefixes_bucket_prefix'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_job_id: Mapped[str] = mapped_column(ForeignKey('scan_jobs.id'), nullable=False, index=True)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    prefix: Mapped[str] = mapped_column(String(1024), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    has_raw_child: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_processed_child: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_episode_grandchild: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_list_candidate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    first_seen_scan_id: Mapped[str | None] = mapped_column(ForeignKey('scan_jobs.id'), nullable=True)
    last_seen_scan_id: Mapped[str] = mapped_column(ForeignKey('scan_jobs.id'), nullable=False)


class ListRecord(Base):
    __tablename__ = 'lists'
    __table_args__ = (UniqueConstraint('bucket', 'list_prefix', name='uq_lists_bucket_list_prefix'),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    list_prefix: Mapped[str] = mapped_column(String(1024), nullable=False)
    confirmed_scan_id: Mapped[str] = mapped_column(ForeignKey('scan_jobs.id'), nullable=False)
    last_active_scan_id: Mapped[str] = mapped_column(ForeignKey('scan_jobs.id'), nullable=False)
    has_raw: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    total_raw_episodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_processed_episodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidate_task_type: Mapped[str] = mapped_column(String(128), default='', nullable=False)
    candidate_source: Mapped[str] = mapped_column(String(32), default='', nullable=False)
    final_task_type_id: Mapped[str | None] = mapped_column(ForeignKey('task_types.id'), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)
    source_status: Mapped[str] = mapped_column(String(32), default='present', nullable=False, index=True)
    missing_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    missing_evidence_shard_id: Mapped[int | None] = mapped_column(ForeignKey('scan_shards.id'), nullable=True)
    first_missing_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_missing_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_confirmed_present_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    final_task_type = relationship('TaskType')
    episode_inventory = relationship('EpisodeInventory', back_populates='list_record')


class EpisodeInventory(Base):
    __tablename__ = 'episode_inventory'
    __table_args__ = (UniqueConstraint('list_id', 'episode_name', name='uq_episode_inventory_list_episode_name'),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    list_id: Mapped[str] = mapped_column(ForeignKey('lists.id'), nullable=False, index=True)
    episode_name: Mapped[str] = mapped_column(String(64), nullable=False)
    episode_prefix: Mapped[str] = mapped_column(String(1024), nullable=False)
    raw_prefix: Mapped[str] = mapped_column(String(1024), default='', nullable=False)
    processed_prefix: Mapped[str] = mapped_column(String(1024), default='', nullable=False)
    state: Mapped[str] = mapped_column(String(32), default='ingestable', nullable=False, index=True)
    raw_exists: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_exists: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), default='', nullable=False)
    metadata_hash: Mapped[str] = mapped_column(String(64), default='', nullable=False)
    episode_id_from_manifest: Mapped[str] = mapped_column(String(128), default='', nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    frame_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    state_changed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    first_seen_scan_id: Mapped[str] = mapped_column(ForeignKey('scan_jobs.id'), nullable=False)
    last_seen_scan_id: Mapped[str] = mapped_column(ForeignKey('scan_jobs.id'), nullable=False)
    ingested_episode_id: Mapped[str | None] = mapped_column(ForeignKey('episodes.id'), nullable=True, index=True)
    max_observed_state: Mapped[str] = mapped_column(String(32), default='ingestable', nullable=False)
    source_status: Mapped[str] = mapped_column(String(32), default='present', nullable=False, index=True)
    missing_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    missing_evidence_shard_id: Mapped[int | None] = mapped_column(ForeignKey('scan_shards.id'), nullable=True)
    first_missing_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_missing_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_confirmed_present_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    raw_source_status: Mapped[str] = mapped_column(String(32), default='present', nullable=False)
    processed_source_status: Mapped[str] = mapped_column(String(32), default='present', nullable=False)
    raw_missing_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_missing_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    raw_missing_evidence_shard_id: Mapped[int | None] = mapped_column(ForeignKey('scan_shards.id'), nullable=True)
    processed_missing_evidence_shard_id: Mapped[int | None] = mapped_column(ForeignKey('scan_shards.id'), nullable=True)
    raw_first_missing_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    processed_first_missing_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    raw_last_missing_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    processed_last_missing_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    raw_object_count: Mapped[int] = mapped_column(BIGINT, default=0, nullable=False)
    processed_object_count: Mapped[int] = mapped_column(BIGINT, default=0, nullable=False)
    raw_total_size_bytes: Mapped[int] = mapped_column(BIGINT, default=0, nullable=False)
    processed_total_size_bytes: Mapped[int] = mapped_column(BIGINT, default=0, nullable=False)
    raw_content_fingerprint: Mapped[str] = mapped_column(String(64), default='', nullable=False)
    processed_content_fingerprint: Mapped[str] = mapped_column(String(64), default='', nullable=False)
    latest_object_modified_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    list_record = relationship('ListRecord', back_populates='episode_inventory')
    objects = relationship('EpisodeObject', back_populates='episode_inventory')
    ingested_episode = relationship('Episode')


class EpisodeObject(Base):
    __tablename__ = 'episode_objects'
    __table_args__ = (UniqueConstraint('episode_inventory_id', 'object_key', name='uq_episode_objects_episode_object_key'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    episode_inventory_id: Mapped[str] = mapped_column(ForeignKey('episode_inventory.id'), nullable=False, index=True)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    object_scope: Mapped[str] = mapped_column(String(16), nullable=False)
    object_role: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BIGINT, default=0, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), default='', nullable=False, index=True)
    last_modified: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_seen_scan_id: Mapped[str] = mapped_column(ForeignKey('scan_jobs.id'), nullable=False)
    source_status: Mapped[str] = mapped_column(String(32), default='present', nullable=False, index=True)
    missing_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    missing_evidence_shard_id: Mapped[int | None] = mapped_column(ForeignKey('scan_shards.id'), nullable=True)
    first_missing_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_missing_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_confirmed_present_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    episode_inventory = relationship('EpisodeInventory', back_populates='objects')


class BatchAssetRollup(Base):
    __tablename__ = 'batch_asset_rollups'

    batch_id: Mapped[str] = mapped_column(ForeignKey('batches.id'), primary_key=True)
    episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_duration_sec: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    duration_covered_episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_missing_episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_frame_count: Mapped[int] = mapped_column(BIGINT, default=0, nullable=False)
    frame_covered_episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    frame_missing_episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sampled_episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reviewed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_pass_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_fail_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qualified_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unqualified_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_dataset_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_episode_updated_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    source_watermark: Mapped[str] = mapped_column(String(128), default='', nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(64), default='batch-asset-rollup-v1', nullable=False)
    refreshed_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)

    batch = relationship('Batch')


class BatchAssetRecomputeJob(Base):
    __tablename__ = 'batch_asset_recompute_jobs'

    batch_id: Mapped[str] = mapped_column(ForeignKey('batches.id'), primary_key=True)
    reason: Mapped[str] = mapped_column(String(64), default='unknown', nullable=False)
    requested_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='pending', nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str] = mapped_column(String(500), default='', nullable=False)
    last_started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    rerun_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    batch = relationship('Batch')


class TaskAssetRollup(Base):
    __tablename__ = 'task_asset_rollups'

    task_type_id: Mapped[str] = mapped_column(ForeignKey('task_types.id'), primary_key=True)
    batch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reviewed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    not_reviewed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_pass_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_fail_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qualified_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unqualified_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_dataset_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_duration_sec: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    duration_covered_episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_missing_episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_frame_count: Mapped[int] = mapped_column(BIGINT, default=0, nullable=False)
    frame_covered_episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    frame_missing_episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sampled_episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accepted_batch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_batch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_batch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_batch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_watermark: Mapped[str] = mapped_column(String(128), default='', nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(64), default='task-asset-rollup-v1', nullable=False)
    refreshed_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)

    task_type = relationship('TaskType')


class TaskAssetRecomputeJob(Base):
    __tablename__ = 'task_asset_recompute_jobs'

    task_type_id: Mapped[str] = mapped_column(ForeignKey('task_types.id'), primary_key=True)
    reason: Mapped[str] = mapped_column(String(64), default='unknown', nullable=False)
    requested_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='pending', nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str] = mapped_column(String(500), default='', nullable=False)
    last_started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    last_finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    rerun_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    task_type = relationship('TaskType')


class ClassificationRule(Base):
    __tablename__ = 'classification_rules'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(String(256), nullable=False)
    target_task_type_id: Mapped[str] = mapped_column(ForeignKey('task_types.id'), nullable=False)
    candidate_label: Mapped[str] = mapped_column(String(128), default='', nullable=False)
    match_scope: Mapped[str] = mapped_column(String(32), default='basename', nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    is_authoritative: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)

    target_task_type = relationship('TaskType')
