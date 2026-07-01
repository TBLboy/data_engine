from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditEvent(Base):
    __tablename__ = 'audit_events'

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operator: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target: Mapped[str] = mapped_column(String(128), nullable=False)
    detail: Mapped[str] = mapped_column(String(500), nullable=False)
    time: Mapped[DateTime] = mapped_column(DateTime(timezone=False), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, default='business_action', server_default='business_action')
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default='info', server_default='info')
    operator_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
