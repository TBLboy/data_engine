from sqlalchemy import DateTime, ForeignKey, Integer, String, Float, Text, func
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
