from sqlalchemy import DateTime, ForeignKey, Integer, String
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
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lock_owner_user_id: Mapped[str] = mapped_column(String(64), default='', nullable=False)
    lock_owner_name: Mapped[str] = mapped_column(String(64), default='', nullable=False)
    lock_acquired_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    lock_expires_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)

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
