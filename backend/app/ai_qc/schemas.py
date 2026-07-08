from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ── 现有 AI Explain 模型 ─────────────────────────────────────────


class QcMetricInput(BaseModel):
    metricId: str
    name: str
    qualityDimension: str
    evidenceId: str = ""
    value: float
    valueText: str = ""
    unit: str = ""
    score: float
    level: str  # good / warn / bad
    description: str = ""
    confidence: float = 1.0
    weight: float = 1.0


class QcTimelineSegmentInput(BaseModel):
    start: float
    end: float
    startSec: float
    endSec: float
    level: str
    label: str
    sourceMetricId: str
    qualityDimension: str = ""


class AiExplainRequest(BaseModel):
    episodeId: str = ""
    qMotionScore: float
    qMotionLevel: str  # good / warn / bad
    weightedScoreBeforeCap: float | None = None
    metrics: list[QcMetricInput] = Field(default_factory=list)
    timelineSegments: list[QcTimelineSegmentInput] = Field(default_factory=list)
    userPrompt: str = ""
    history: list[dict[str, str]] = Field(default_factory=list)


class QcIssue(BaseModel):
    metricId: str
    name: str
    score: float
    level: str
    evidence: str


class QcOverallFacts(BaseModel):
    finalScore: float
    weightedScoreBeforeCap: float | None = None
    level: str
    capTriggered: bool = False
    capReason: str = ""


class QcFacts(BaseModel):
    overall: QcOverallFacts
    topIssues: list[QcIssue] = Field(default_factory=list)
    normalEvidence: list[str] = Field(default_factory=list)
    reviewSuggestion: str = ""


class AiExplainResponse(BaseModel):
    enabled: bool = True
    source: str = "template"  # template / llm / unavailable
    model: str | None = None
    latencyMs: int = 0
    explanation: str = ""
    fallbackUsed: bool = False
    mentionedMetricIds: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ── Phase 1: Conversation / Chat 模型 ─────────────────────────────


class PageState(BaseModel):
    """用户在 manual QC 页面的当前视图状态。"""
    selectedMetricId: str = ""
    currentVideoTimeSec: float | None = None
    selectedTimelineSegmentId: str = ""
    visibleChart: str = ""  # e.g. "left_arm_qpos", "right_hand_actions"
    openedMetricPanel: str = ""  # e.g. "MQ", "LQ", "DI", "DX"


class AiChatRequest(BaseModel):
    """POST /api/ai-assistant/chat 请求体。"""
    conversationId: str = ""  # 空则自动创建新对话
    episodeId: str = ""
    message: str = ""
    pageState: PageState | None = None
    # QC 数据（首次创建 conversation 时带上，后续可省略）
    qMotionScore: float | None = None
    qMotionLevel: str | None = None
    weightedScoreBeforeCap: float | None = None
    metrics: list[QcMetricInput] = Field(default_factory=list)
    timelineSegments: list[QcTimelineSegmentInput] = Field(default_factory=list)
    stream: bool = True


class AiConversationListItem(BaseModel):
    """对话列表项。"""
    conversationId: str
    episodeId: str
    title: str | None = None
    status: str = "active"
    messageCount: int = 0
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class AiMessageItem(BaseModel):
    """单条消息。"""
    id: str
    role: str  # user / assistant / system
    content: str
    provider: str | None = None
    model: str | None = None
    latencyMs: int | None = None
    createdAt: datetime | None = None


class AiConversationDetail(BaseModel):
    """对话详情（含消息列表）。"""
    conversationId: str
    episodeId: str
    title: str | None = None
    status: str = "active"
    messages: list[AiMessageItem] = Field(default_factory=list)


class AiChatResponse(BaseModel):
    """POST /api/ai-assistant/chat 响应。"""
    messageId: str
    conversationId: str
    status: str = "completed"  # completed / tool_running / error
    answer: str = ""
    source: str = "template"  # template / llm / unavailable
    model: str | None = None
    latencyMs: int = 0
    fallbackUsed: bool = False
    warnings: list[str] = Field(default_factory=list)
