from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Batch(Base):
    __tablename__ = 'batches'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_type_id: Mapped[str] = mapped_column(ForeignKey('task_types.id'), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    imported_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)
    episode_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sampled_episode_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dispatch_mode: Mapped[str] = mapped_column(String(32), default='sampled', nullable=False)
    sampling_ratio: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    active_dispatch_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qc_status: Mapped[str] = mapped_column(String(32), default='new', nullable=False)
    pass_rate: Mapped[float] = mapped_column(nullable=False, default=0)
    top_reason: Mapped[str] = mapped_column(String(128), default='-', nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ── Batch adjudication fields ──
    manual_pass_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_fail_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    reject_threshold: Mapped[float] = mapped_column(Float, default=0.10, nullable=False)
    failure_rate_denominator: Mapped[str] = mapped_column(String(32), default='SAMPLED_COUNT', nullable=False)
    batch_decision: Mapped[str] = mapped_column(String(32), default='PENDING', nullable=False)
    batch_decision_reason: Mapped[str] = mapped_column(Text, default='', nullable=False)
    decision_policy_version: Mapped[str] = mapped_column(String(64), default='batch-reject-v1', nullable=False)
    adjudicated_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    task_type = relationship('TaskType', back_populates='batches')
    episodes = relationship('Episode', back_populates='batch')
    qc_tasks = relationship('QcTask', back_populates='batch')
    decision_logs = relationship('BatchDecisionLog', back_populates='batch')
