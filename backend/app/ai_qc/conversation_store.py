"""AI 助手对话持久化。

Phase 1: 基础 CRUD + 消息持久化
Phase 2+: memory summaries, tool runs
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.ai_assistant import AiConversation, AiMessage

logger = logging.getLogger(__name__)

MAX_MESSAGES_PER_CONVERSATION = 200


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Conversation CRUD ──────────────────────────────────────────────


def get_or_create_conversation(
    db: Session,
    *,
    episode_id: str,
    user_id: str,
    title: str | None = None,
) -> AiConversation:
    """获取该 episode 下该用户最近的活跃对话，没有则创建。"""
    existing = (
        db.query(AiConversation)
        .filter(
            AiConversation.episode_id == episode_id,
            AiConversation.user_id == user_id,
            AiConversation.status == "active",
        )
        .order_by(AiConversation.updated_at.desc())
        .first()
    )
    if existing:
        existing.updated_at = _utcnow()
        db.commit()
        return existing

    conv = AiConversation(
        episode_id=episode_id,
        user_id=user_id,
        title=title,
        status="active",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_conversation(db: Session, conversation_id: str) -> AiConversation | None:
    return db.query(AiConversation).filter(AiConversation.id == conversation_id).first()


def get_conversation_messages(
    db: Session,
    conversation_id: str,
    limit: int = 50,
) -> list[AiMessage]:
    return (
        db.query(AiMessage)
        .filter(AiMessage.conversation_id == conversation_id)
        .order_by(AiMessage.created_at.asc())
        .limit(limit)
        .all()
    )


def list_user_conversations(
    db: Session,
    user_id: str,
    episode_id: str | None = None,
    limit: int = 10,
) -> list[AiConversation]:
    q = (
        db.query(AiConversation)
        .filter(AiConversation.user_id == user_id)
    )
    if episode_id:
        q = q.filter(AiConversation.episode_id == episode_id)
    return q.order_by(AiConversation.updated_at.desc()).limit(limit).all()


# ── Message CRUD ───────────────────────────────────────────────────


def add_message(
    db: Session,
    *,
    conversation_id: str,
    episode_id: str,
    user_id: str | None,
    role: str,
    content: str,
    content_json: dict | None = None,
    provider: str | None = None,
    model: str | None = None,
    latency_ms: int | None = None,
) -> AiMessage:
    """添加一条消息并更新 conversation 的 updated_at。"""
    msg = AiMessage(
        conversation_id=conversation_id,
        episode_id=episode_id,
        user_id=user_id,
        role=role,
        content=content,
        content_json=content_json,
        provider=provider,
        model=model,
        latency_ms=latency_ms,
    )
    db.add(msg)

    # 更新 conversation 时间戳
    conv = db.query(AiConversation).filter(AiConversation.id == conversation_id).first()
    if conv:
        conv.updated_at = _utcnow()

    db.commit()
    db.refresh(msg)

    # 自动修剪旧消息
    _trim_old_messages(db, conversation_id)

    return msg


def get_recent_messages(
    db: Session,
    conversation_id: str,
    limit: int = 12,
) -> list[AiMessage]:
    """获取最近 N 条消息，用于构建对话历史。"""
    return (
        db.query(AiMessage)
        .filter(AiMessage.conversation_id == conversation_id)
        .order_by(AiMessage.created_at.desc())
        .limit(limit)
        .all()[::-1]  # 反转为时间正序
    )


def _trim_old_messages(db: Session, conversation_id: str) -> None:
    """保留最近 MAX_MESSAGES 条，删除更早的消息。"""
    total = (
        db.query(AiMessage)
        .filter(AiMessage.conversation_id == conversation_id)
        .count()
    )
    if total <= MAX_MESSAGES_PER_CONVERSATION:
        return

    # 找到需要保留的最早消息的 created_at
    keep_since = (
        db.query(AiMessage.created_at)
        .filter(AiMessage.conversation_id == conversation_id)
        .order_by(AiMessage.created_at.desc())
        .offset(MAX_MESSAGES_PER_CONVERSATION - 1)
        .limit(1)
        .scalar()
    )
    if keep_since:
        deleted = (
            db.query(AiMessage)
            .filter(
                AiMessage.conversation_id == conversation_id,
                AiMessage.created_at < keep_since,
            )
            .delete(synchronize_session="fetch")
        )
        db.commit()
        if deleted:
            logger.info("Trimmed %d old messages from conversation %s", deleted, conversation_id)
