from sqlalchemy import DateTime, ForeignKey, Integer, String
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
    qc_status: Mapped[str] = mapped_column(String(32), default='new', nullable=False)
    pass_rate: Mapped[float] = mapped_column(nullable=False, default=0)
    top_reason: Mapped[str] = mapped_column(String(128), default='-', nullable=False)
    storage_path: Mapped[str] = mapped_column(String(255), nullable=False)

    task_type = relationship('TaskType', back_populates='batches')
    episodes = relationship('Episode', back_populates='batch')
    qc_tasks = relationship('QcTask', back_populates='batch')
