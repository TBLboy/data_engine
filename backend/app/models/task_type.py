from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class TaskType(Base):
    __tablename__ = 'task_types'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    total_batches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_episodes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    batches = relationship('Batch', back_populates='task_type')
