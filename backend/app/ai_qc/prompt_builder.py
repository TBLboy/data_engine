"""Prompt 构造函数。

将事实数据转换为 LLM 可理解的文本，支持多轮对话。
"""

from __future__ import annotations

from app.ai_qc.schemas import QcFacts


def build_prompt(
    facts: QcFacts,
    user_prompt: str = "",
    history: list[dict[str, str]] | None = None,
    page_state: str = "",
) -> str:
    """构建发给 LLM 的完整 prompt。

    Args:
        facts: 当前 episode 的质检事实
        user_prompt: 质检员当前输入的问题
        history: 之前的对话记录（role/content 格式），最多保留最近 3 轮
        page_state: 当前页面状态文本（用户正在看什么指标/时间段/曲线）
    """
    summary = _build_facts_summary(facts)

    system = """你是 Robot QC V1 的质检助手，帮助质检员理解和分析自动检测结果。

核心行为准则：
- 质检员问什么就答什么，不要每次都复述完整检测报告
- 如果质检员只是打招呼（"你好"、"哈喽"等），简单友好地回应即可，不需要提数据
- 如果质检员问某个概念（如"数据完整性是什么"、"DI-02 什么意思"），用通俗语言解释这个概念，可以顺便提一下当前数据中的相关情况
- 如果质检员问具体指标或异常原因，只回答相关部分，不要铺开讲所有指标
- 回答简短直接（2-5句话），不要啰嗦
- 中文回答，语气像同事交流，不要像写报告

硬约束：
- 涉及数据时，只能引用当前 episode 的数据，不要编造
- 不要输出 Markdown 标题、列表格式或 JSON
- 不要给出 pass/fail 判定"""

    # 构建对话历史
    history_text = ""
    if history:
        recent = history[-6:]  # 最近 3 轮
        lines = []
        for msg in recent:
            role_label = "质检员" if msg.get("role") == "user" else "助手"
            content = msg.get("content", "")
            if content.strip():
                lines.append(f"{role_label}：{content.strip()}")
        if lines:
            history_text = "\n".join(lines) + "\n"

    if user_prompt and user_prompt.strip():
        hdr_parts = []
        if page_state:
            hdr_parts.append(f"【页面状态】\n{page_state}")
        if history_text:
            hdr_parts.append(f"【对话记录】\n{history_text}")
        hdr = "\n\n".join(hdr_parts) + "\n" if hdr_parts else ""
        return f"""{system}

{hdr}【当前 Episode 数据】
{summary}

质检员说：{user_prompt.strip()}

请直接回答质检员的问题（简短、有针对性，不要复述完整报告）："""

    # 无用户提问：首次解释
    hdr_parts = []
    if page_state:
        hdr_parts.append(f"【页面状态】\n{page_state}")
    if history_text:
        hdr_parts.append(f"【对话记录】\n{history_text}")
    hdr = "\n\n".join(hdr_parts) + "\n" if hdr_parts else ""
    return f"""{system}

{hdr}【当前 Episode 数据】
{summary}

请用2-3句话概括当前数据的关键质量问题和建议的排查方向："""


def _build_facts_summary(facts: QcFacts) -> str:
    """构造简洁的文本摘要，替代 JSON 格式。

    文本格式对 7B 小模型更友好，不会被 JSON 结构淹没。
    """
    lines = []
    overall = facts.overall
    lines.append(f"Q_motion: {overall.finalScore}分, 等级{overall.level}")

    if overall.capTriggered:
        lines.append(f"封顶: 是（{overall.capReason}）")
    else:
        lines.append("封顶: 否")

    if facts.topIssues:
        lines.append("异常指标:")
        for issue in facts.topIssues[:5]:
            evidence = issue.evidence[:200] if issue.evidence else f"{issue.name} {issue.score}分"
            lines.append(f"  {issue.metricId}「{issue.name}」{issue.score}分({issue.level}) - {evidence}")

    if facts.normalEvidence:
        lines.append("正常指标:")
        for ev in facts.normalEvidence[:5]:
            lines.append(f"  {ev}")

    if facts.reviewSuggestion:
        lines.append(f"建议: {facts.reviewSuggestion}")

    return "\n".join(lines)
