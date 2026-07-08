"""AI QC Explain 主服务。

职责编排：facts → template → (optional LLM) → response。
默认走 template，LLM 失败自动 fallback。
"""

from __future__ import annotations

import logging
import time

from app.ai_qc.facts_builder import build_qc_facts
from app.ai_qc.llm_client import call_ollama
from app.ai_qc.prompt_builder import build_prompt
from app.ai_qc.schemas import AiExplainRequest, AiExplainResponse
from app.ai_qc.template_renderer import render_template
from app.ai_qc.validator import validate_llm_output

logger = logging.getLogger(__name__)


class AiQcService:
    def __init__(
        self,
        *,
        enabled: bool = False,
        ollama_base_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5:7b",
        timeout_seconds: int = 10,
    ):
        self.enabled = enabled
        self.ollama_base_url = ollama_base_url
        self.ollama_model = ollama_model
        self.timeout_seconds = timeout_seconds

    def explain(self, request: AiExplainRequest) -> AiExplainResponse:
        t0 = time.monotonic()

        # 1. 构建事实
        facts = build_qc_facts(request)
        mentioned_ids = [i.metricId for i in facts.topIssues]

        # 2. 生成模板解释
        template_text = render_template(facts)

        # 3. 如果 LLM 未启用，直接返回模板
        if not self.enabled:
            latency_ms = int((time.monotonic() - t0) * 1000)
            return AiExplainResponse(
                enabled=False,
                source="template",
                model=None,
                latencyMs=latency_ms,
                explanation=template_text,
                fallbackUsed=False,
                mentionedMetricIds=mentioned_ids,
                warnings=[],
            )

        # 4. 调用 LLM 润色
        prompt = build_prompt(facts, user_prompt=request.userPrompt, history=request.history)
        llm_result = call_ollama(
            prompt,
            base_url=self.ollama_base_url,
            model=self.ollama_model,
            timeout_seconds=self.timeout_seconds,
        )

        # 5. LLM 失败 → fallback
        if llm_result is None:
            latency_ms = int((time.monotonic() - t0) * 1000)
            return AiExplainResponse(
                enabled=True,
                source="template",
                model=self.ollama_model,
                latencyMs=latency_ms,
                explanation=template_text,
                fallbackUsed=True,
                mentionedMetricIds=mentioned_ids,
                warnings=["LLM 调用失败，使用模板解释"],
            )

        # 6. 校验 LLM 输出
        valid, warnings = validate_llm_output(
            llm_result.text, facts, is_conversation=bool(request.userPrompt and request.userPrompt.strip())
        )
        if not valid:
            latency_ms = int((time.monotonic() - t0) * 1000)
            return AiExplainResponse(
                enabled=True,
                source="template",
                model=self.ollama_model,
                latencyMs=latency_ms,
                explanation=template_text,
                fallbackUsed=True,
                mentionedMetricIds=mentioned_ids,
                warnings=warnings,
            )

        # 7. LLM 输出有效
        latency_ms = llm_result.latency_ms
        return AiExplainResponse(
            enabled=True,
            source="llm",
            model=self.ollama_model,
            latencyMs=latency_ms,
            explanation=llm_result.text,
            fallbackUsed=False,
            mentionedMetricIds=mentioned_ids,
            warnings=[],
        )
