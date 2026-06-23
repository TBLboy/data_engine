from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class IngestJob(Base):
    __tablename__ = 'ingest_jobs'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    batch_name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_path: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    episodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    imported_episodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_episodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detail: Mapped[str] = mapped_column(String(500), default='', nullable=False)
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=False), nullable=True)
