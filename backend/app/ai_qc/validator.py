"""LLM 输出校验。

校验失败时返回 (False, warnings)，由 service 层 fallback 到 template。
对话模式（有 user_prompt）下放宽部分约束。
"""

from __future__ import annotations

from app.ai_qc.schemas import QcFacts


MAX_CHARS = 400
FORBIDDEN_PATTERNS = [
    ("建议判 fail", "越权建议 fail"),
    ("建议直接通过", "越权建议通过"),
    ("判定为不合格", "越权结论"),
    ("判定为合格", "越权结论"),
]


def validate_llm_output(
    text: str,
    facts: QcFacts,
    *,
    is_conversation: bool = False,
) -> tuple[bool, list[str]]:
    """校验 LLM 输出质量。

    Args:
        text: LLM 返回的文本
        facts: 当前 episode 的质检事实
        is_conversation: 是否为对话模式的响应（用户有提问），
                         对话模式下不强制要求提及封顶/截断
    """
    warnings: list[str] = []

    if not text or not text.strip():
        warnings.append("输出为空")
        return False, warnings

    stripped = text.strip()

    if len(stripped) > MAX_CHARS:
        warnings.append(f"输出过长 ({len(stripped)} > {MAX_CHARS})")

    for pattern, reason in FORBIDDEN_PATTERNS:
        if pattern in stripped:
            warnings.append(f"包含禁止内容: {reason}")

    # capTriggered 时需提及封顶/截断，但对话模式下不强制
    # （因为用户可能问的是其他问题，不涉及 cap）
    if not is_conversation and facts.overall.capTriggered:
        if "封顶" not in stripped and "截断" not in stripped:
            warnings.append("capTriggered=true 但输出未提及封顶/截断")

    if warnings:
        return False, warnings

    return True, []
