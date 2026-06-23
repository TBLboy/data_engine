from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Episode(Base):
    __tablename__ = 'episodes'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('batches.id'), nullable=False, index=True)
    task_name: Mapped[str] = mapped_column(String(128), nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False)
    qc_status: Mapped[str] = mapped_column(String(32), default='new', nullable=False)
    qc_result: Mapped[str] = mapped_column(String(32), default='pending', nullable=False)
    reviewer: Mapped[str] = mapped_column(String(64), default='-', nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), default='-', nullable=False)
    source_path: Mapped[str] = mapped_column(String(255), default='', nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), default='', nullable=False, index=True)
    ingest_status: Mapped[str] = mapped_column(String(32), default='indexed', nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)
    in_candidate_pool: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sampled_for_qc: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    batch = relationship('Batch', back_populates='episodes')
    qc_tasks = relationship('QcTask', back_populates='episode')
    revisions = relationship('QcReviewRevision', back_populates='episode')
