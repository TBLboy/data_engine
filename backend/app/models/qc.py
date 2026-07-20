from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Float, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class QcTask(Base):
    __tablename__ = 'qc_tasks'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey('episodes.id'), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('batches.id'), nullable=False, index=True)
    batch_name: Mapped[str] = mapped_column(String(128), nullable=False)
    task_name: Mapped[str] = mapped_column(String(128), nullable=False)
    assignee: Mapped[str] = mapped_column(String(64), default='未派发', nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='new', nullable=False)
    priority: Mapped[str] = mapped_column(String(32), default='normal', nullable=False)
    dispatch_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    sampling_ratio: Mapped[int] = mapped_column(Integer, nullable=False)
    dispatch_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    assignment_mode: Mapped[str] = mapped_column(String(32), default='manual', nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lock_owner_user_id: Mapped[str] = mapped_column(String(64), default='', nullable=False)
    lock_owner_name: Mapped[str] = mapped_column(String(64), default='', nullable=False)
    lock_acquired_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    lock_expires_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False, default=func.now(), onupdate=func.now())

    episode = relationship('Episode', back_populates='qc_tasks')
    batch = relationship('Batch', back_populates='qc_tasks')


class QcReviewRevision(Base):
    __tablename__ = 'qc_review_revisions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey('episodes.id'), nullable=False, index=True)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    primary_reason: Mapped[str] = mapped_column(String(128), default='-', nullable=False)
    operator: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str] = mapped_column(String(500), default='', nullable=False)
    time: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)

    episode = relationship('Episode', back_populates='revisions')


class BatchDecisionLog(Base):
    __tablename__ = 'batch_decision_log'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('batches.id'), nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(64), default='batch-reject-v1', nullable=False)
    reject_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    failure_rate_denominator: Mapped[str] = mapped_column(String(32), nullable=False)
    total_episode_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sampled_episode_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewed_episode_count: Mapped[int] = mapped_column(Integer, nullable=False)
    manual_pass_count: Mapped[int] = mapped_column(Integer, nullable=False)
    manual_fail_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_rate: Mapped[float] = mapped_column(Float, nullable=False)
    batch_decision: Mapped[str] = mapped_column(String(32), nullable=False)
    decision_reason: Mapped[str] = mapped_column(Text, default='', nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), server_default=func.now())

    batch = relationship('Batch', back_populates='decision_logs')


class DatasetExportJob(Base):
    __tablename__ = 'dataset_export_jobs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_type_id: Mapped[str] = mapped_column(String(64), nullable=False)
    export_type: Mapped[str] = mapped_column(String(32), default='qualified_dataset', nullable=False)
    export_format: Mapped[str] = mapped_column(String(16), nullable=False)
    episode_count: Mapped[int] = mapped_column(Integer, nullable=False)
    annotation_completed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    training_default_included_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    filters_json: Mapped[str] = mapped_column(Text, default='{}', nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), server_default=func.now())

    items = relationship('DatasetExportItem', back_populates='export_job', cascade='all, delete-orphan')


class DatasetExportItem(Base):
    __tablename__ = 'dataset_export_items'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    export_job_id: Mapped[int] = mapped_column(ForeignKey('dataset_export_jobs.id'), nullable=False, index=True)
    episode_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    inclusion_status: Mapped[str] = mapped_column(String(32), default='included', nullable=False)
    episode_snapshot_json: Mapped[str] = mapped_column(Text, default='{}', nullable=False)
    annotation_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    annotation_status: Mapped[str] = mapped_column(String(32), default='not_created', nullable=False)
    training_default_included: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    annotation_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    annotation_revision_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schema_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    task_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), server_default=func.now())

    export_job = relationship('DatasetExportJob', back_populates='items')


class TaskOperationLog(Base):
    __tablename__ = 'task_operation_log'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    episode_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    from_reviewer: Mapped[str] = mapped_column(String(64), default='', nullable=False)
    to_reviewer: Mapped[str] = mapped_column(String(64), default='', nullable=False)
    operator_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default='', nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), server_default=func.now())


class QcRereviewRequest(Base):
    __tablename__ = 'qc_rereview_requests'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey('episodes.id'), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    requester_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    requester_name: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default='', nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='pending', nullable=False, index=True)
    approver_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approver_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default='', nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), server_default=func.now())
    decided_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class BugReport(Base):
    __tablename__ = 'bug_reports'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(Text, default='', nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='open', nullable=False, index=True)
    image_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_content_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reporter_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reporter_name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False, default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False, default=func.now(), onupdate=func.now())
