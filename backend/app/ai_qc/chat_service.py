"""AI Chat 服务。

编排 conversation → evidence → LLM → persist → response 完整链路。
支持流式 (SSE) 输出和 template fallback。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator

from sqlalchemy.orm import Session

from app.ai_qc.conversation_store import (
    add_message,
    get_or_create_conversation,
    get_recent_messages,
)
from app.ai_qc.facts_builder import build_qc_facts
from app.ai_qc.llm_client import LlmResult, call_ollama, call_ollama_stream
from app.ai_qc.prompt_builder import build_prompt
from app.ai_qc.schemas import (
    AiChatRequest,
    AiChatResponse,
    AiConversationDetail,
    AiConversationListItem,
    AiExplainRequest,
    AiMessageItem,
    PageState,
)
from app.ai_qc.template_renderer import render_template
from app.ai_qc.validator import validate_llm_output

logger = logging.getLogger(__name__)


class AiChatService:
    def __init__(
        self,
        *,
        enabled: bool = False,
        ollama_base_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5:7b",
        timeout_seconds: int = 30,
    ):
        self.enabled = enabled
        self.ollama_base_url = ollama_base_url
        self.ollama_model = ollama_model
        self.timeout_seconds = timeout_seconds

    # ── Conversation API ────────────────────────────────────────────

    def list_conversations(
        self, db: Session, user_id: str, episode_id: str | None = None
    ) -> list[AiConversationListItem]:
        from app.ai_qc.conversation_store import list_user_conversations
        convs = list_user_conversations(db, user_id, episode_id)
        result = []
        for c in convs:
            msg_count = len(c.messages) if c.messages else 0
            result.append(AiConversationListItem(
                conversationId=c.id,
                episodeId=c.episode_id,
                title=c.title,
                status=c.status,
                messageCount=msg_count,
                createdAt=c.created_at,
                updatedAt=c.updated_at,
            ))
        return result

    def get_conversation_detail(
        self, db: Session, conversation_id: str
    ) -> AiConversationDetail | None:
        from app.ai_qc.conversation_store import get_conversation, get_conversation_messages
        conv = get_conversation(db, conversation_id)
        if conv is None:
            return None
        msgs = get_conversation_messages(db, conversation_id, limit=50)
        return AiConversationDetail(
            conversationId=conv.id,
            episodeId=conv.episode_id,
            title=conv.title,
            status=conv.status,
            messages=[
                AiMessageItem(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    provider=m.provider,
                    model=m.model,
                    latencyMs=m.latency_ms,
                    createdAt=m.created_at,
                )
                for m in msgs
            ],
        )

    # ── Chat API ────────────────────────────────────────────────────

    def chat(self, db: Session, request: AiChatRequest, user_id: str) -> AiChatResponse:
        t0 = time.monotonic()

        # 1. 获取或创建 conversation
        conv = get_or_create_conversation(
            db,
            episode_id=request.episodeId,
            user_id=user_id,
        )

        # 2. 保存用户消息
        add_message(
            db,
            conversation_id=conv.id,
            episode_id=request.episodeId,
            user_id=user_id,
            role="user",
            content=request.message,
        )

        # 3. 构建事实（如果有 QC 数据）
        has_qc_data = request.qMotionScore is not None and request.qMotionLevel is not None
        facts = None
        mentioned_ids: list[str] = []
        template_text = ""

        if has_qc_data:
            explain_req = AiExplainRequest(
                episodeId=request.episodeId,
                qMotionScore=request.qMotionScore or 0,
                qMotionLevel=request.qMotionLevel or "good",
                weightedScoreBeforeCap=request.weightedScoreBeforeCap,
                metrics=request.metrics,
                timelineSegments=request.timelineSegments,
                userPrompt=request.message,
            )
            facts = build_qc_facts(explain_req)
            mentioned_ids = [i.metricId for i in facts.topIssues]
            template_text = render_template(facts)

        # 4. 构建对话历史
        db_messages = get_recent_messages(db, conv.id, limit=12)
        history = [
            {"role": m.role, "content": m.content}
            for m in db_messages
            if m.role in ("user", "assistant")
        ]

        # 5. 调用 LLM（或 fallback）
        if not self.enabled or not has_qc_data or facts is None:
            # 无 QC 数据或未启用 → template
            answer = template_text or "当前 episode 数据不可用，无法生成解释。"
            latency_ms = int((time.monotonic() - t0) * 1000)
            assistant_msg = add_message(
                db, conversation_id=conv.id, episode_id=request.episodeId,
                user_id=user_id, role="assistant", content=answer,
                provider="template", latency_ms=latency_ms,
            )
            return AiChatResponse(
                messageId=assistant_msg.id,
                conversationId=conv.id,
                status="completed",
                answer=answer,
                source="template",
                latencyMs=latency_ms,
            )

        # 6. 构建 prompt 并调用 LLM
        page_state_text = _format_page_state(request.pageState)
        prompt = build_prompt(
            facts,
            user_prompt=request.message,
            history=history,
            page_state=page_state_text,
        )

        llm_result = call_ollama(
            prompt,
            base_url=self.ollama_base_url,
            model=self.ollama_model,
            timeout_seconds=self.timeout_seconds,
        )

        # 7. LLM 失败 → fallback
        if llm_result is None:
            latency_ms = int((time.monotonic() - t0) * 1000)
            assistant_msg = add_message(
                db, conversation_id=conv.id, episode_id=request.episodeId,
                user_id=user_id, role="assistant", content=template_text,
                provider="template", latency_ms=latency_ms,
                content_json={"fallbackReason": "LLM 调用失败"},
            )
            return AiChatResponse(
                messageId=assistant_msg.id,
                conversationId=conv.id,
                status="completed",
                answer=template_text,
                source="template",
                model=self.ollama_model,
                latencyMs=latency_ms,
                fallbackUsed=True,
                warnings=["LLM 调用失败，使用模板解释"],
            )

        # 8. 校验 LLM 输出
        valid, warnings = validate_llm_output(
            llm_result.text, facts,
            is_conversation=bool(request.message and request.message.strip()),
        )
        if not valid:
            latency_ms = int((time.monotonic() - t0) * 1000)
            assistant_msg = add_message(
                db, conversation_id=conv.id, episode_id=request.episodeId,
                user_id=user_id, role="assistant", content=template_text,
                provider="llm", model=self.ollama_model, latency_ms=latency_ms,
                content_json={"fallbackReason": "校验失败", "warnings": warnings},
            )
            return AiChatResponse(
                messageId=assistant_msg.id,
                conversationId=conv.id,
                status="completed",
                answer=template_text,
                source="template",
                model=self.ollama_model,
                latencyMs=latency_ms,
                fallbackUsed=True,
                warnings=warnings,
            )

        # 9. LLM 输出有效 → 保存并返回
        latency_ms = llm_result.latency_ms
        assistant_msg = add_message(
            db, conversation_id=conv.id, episode_id=request.episodeId,
            user_id=user_id, role="assistant", content=llm_result.text,
            provider="llm", model=self.ollama_model, latency_ms=latency_ms,
        )
        return AiChatResponse(
            messageId=assistant_msg.id,
            conversationId=conv.id,
            status="completed",
            answer=llm_result.text,
            source="llm",
            model=self.ollama_model,
            latencyMs=latency_ms,
            mentionedMetricIds=mentioned_ids,
        )

    # ── Streaming Chat ──────────────────────────────────────────────

    def chat_stream(
        self, db: Session, request: AiChatRequest, user_id: str
    ) -> Generator[str, None, None]:
        """流式 chat，返回 SSE 事件字符串。"""
        t0 = time.monotonic()

        # 1. conversation
        conv = get_or_create_conversation(db, episode_id=request.episodeId, user_id=user_id)

        # 2. 保存 user message
        add_message(db, conversation_id=conv.id, episode_id=request.episodeId,
                     user_id=user_id, role="user", content=request.message)

        # 3. 构建 facts
        has_qc_data = request.qMotionScore is not None and request.qMotionLevel is not None
        facts = None
        template_text = ""
        if has_qc_data:
            explain_req = AiExplainRequest(
                episodeId=request.episodeId,
                qMotionScore=request.qMotionScore or 0,
                qMotionLevel=request.qMotionLevel or "good",
                weightedScoreBeforeCap=request.weightedScoreBeforeCap,
                metrics=request.metrics,
                timelineSegments=request.timelineSegments,
                userPrompt=request.message,
            )
            facts = build_qc_facts(explain_req)
            template_text = render_template(facts)

        # 4. 对话历史
        db_messages = get_recent_messages(db, conv.id, limit=12)
        history = [
            {"role": m.role, "content": m.content}
            for m in db_messages
            if m.role in ("user", "assistant")
        ]

        # 5. 判断是否可以调用 LLM
        if not self.enabled or not has_qc_data or facts is None:
            answer = template_text or "当前 episode 数据不可用。"
            yield _sse_event("status", {"phase": "completed"})
            yield _sse_event("text", {"text": answer})
            yield _sse_event("done", {})
            assistant_msg = add_message(
                db, conversation_id=conv.id, episode_id=request.episodeId,
                user_id=user_id, role="assistant", content=answer,
                provider="template",
            )
            yield _sse_event("meta", {
                "messageId": assistant_msg.id,
                "conversationId": conv.id,
                "source": "template",
            })
            return

        # 6. 构建 prompt
        page_state_text = _format_page_state(request.pageState)
        prompt = build_prompt(facts, user_prompt=request.message, history=history,
                              page_state=page_state_text)

        yield _sse_event("status", {"phase": "thinking"})

        # 7. 流式调用 LLM
        full_text = ""
        stream_generator = call_ollama_stream(
            prompt,
            base_url=self.ollama_base_url,
            model=self.ollama_model,
            timeout_seconds=self.timeout_seconds,
        )

        if stream_generator is None:
            # Fallback
            yield _sse_event("status", {"phase": "fallback"})
            yield _sse_event("text", {"text": template_text})
            yield _sse_event("done", {})
            assistant_msg = add_message(
                db, conversation_id=conv.id, episode_id=request.episodeId,
                user_id=user_id, role="assistant", content=template_text,
                provider="template",
                content_json={"fallbackReason": "LLM 流式调用失败"},
            )
            yield _sse_event("meta", {
                "messageId": assistant_msg.id, "conversationId": conv.id,
                "source": "template", "fallbackUsed": True,
            })
            return

        for chunk_kind, chunk_text in stream_generator:
            if chunk_kind == "think":
                # 思考过程不发内容给前端，但发 heartbeat 保持连接不断开
                yield _sse_event("status", {"phase": "thinking"})
            else:
                full_text += chunk_text
                yield _sse_event("text", {"text": chunk_text})

        # 8. 校验 + 保存
        valid, warnings = validate_llm_output(
            full_text, facts,
            is_conversation=bool(request.message and request.message.strip()),
        )
        if not valid:
            # 校验失败但流式已经输出了，保存原始回复并标注
            assistant_msg = add_message(
                db, conversation_id=conv.id, episode_id=request.episodeId,
                user_id=user_id, role="assistant", content=full_text,
                provider="llm", model=self.ollama_model,
                content_json={"warnings": warnings},
            )
            yield _sse_event("meta", {
                "messageId": assistant_msg.id, "conversationId": conv.id,
                "source": "llm", "warnings": warnings,
            })
        else:
            assistant_msg = add_message(
                db, conversation_id=conv.id, episode_id=request.episodeId,
                user_id=user_id, role="assistant", content=full_text,
                provider="llm", model=self.ollama_model,
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
            yield _sse_event("meta", {
                "messageId": assistant_msg.id, "conversationId": conv.id,
                "source": "llm",
            })

        yield _sse_event("done", {})


# ── Helpers ────────────────────────────────────────────────────────


def _format_page_state(page_state: PageState | None) -> str:
    """将 pageState 格式化为 prompt 可用的文本。"""
    if page_state is None:
        return ""
    parts = []
    if page_state.selectedMetricId:
        parts.append(f"质检员当前查看的指标: {page_state.selectedMetricId}")
    if page_state.currentVideoTimeSec is not None:
        parts.append(f"视频当前时间: {page_state.currentVideoTimeSec:.1f}s")
    if page_state.selectedTimelineSegmentId:
        parts.append(f"选中的异常时间段: {page_state.selectedTimelineSegmentId}")
    if page_state.visibleChart:
        parts.append(f"当前可见曲线: {page_state.visibleChart}")
    return "\n".join(parts)


def _sse_event(event: str, data: dict) -> str:
    import json
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
