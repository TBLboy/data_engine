from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class TaskType(Base):
    __tablename__ = 'task_types'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    arm_mode: Mapped[str] = mapped_column(String(32), default='both_arms', nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_published_sub_goal_schema_id: Mapped[str | None] = mapped_column(
        ForeignKey('sub_goal_schemas.id'), nullable=True
    )

    batches = relationship('Batch', back_populates='task_type')
