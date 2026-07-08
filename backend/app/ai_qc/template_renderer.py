from __future__ import annotations

from app.ai_qc.schemas import QcFacts


def render_template(facts: QcFacts) -> str:
    overall = facts.overall

    # 场景 A：DI 严重问题，触发 3.0 封顶
    if overall.capTriggered and overall.finalScore <= 3.0:
        top = facts.topIssues[0] if facts.topIssues else None
        if top:
            return (
                f"本段数据整体质量较差，主要原因是{top.metricId}「{top.name}」得分 {top.score:.1f}，"
                f"低于 {3.0} 阈值，触发数据完整性截断规则，Q_motion 被封顶为 {overall.finalScore:.1f}。"
                f"建议优先查看相关异常片段，并确认数据采集过程是否正常。"
            )
        return (
            f"本段数据整体质量较差，数据完整性指标低于 {3.0} 阈值，"
            f"触发截断规则，Q_motion 被封顶为 {overall.finalScore:.1f}。"
            f"建议重点排查数据采集链路是否存在问题。"
        )

    # 场景 B：DI 警告问题，触发 6.0 封顶
    if overall.capTriggered and overall.finalScore <= 6.0:
        top = facts.topIssues[0] if facts.topIssues else None
        if top:
            return (
                f"本段数据需要关注，主要问题是{top.metricId}「{top.name}」得分 {top.score:.1f}，"
                f"触发数据完整性截断规则，Q_motion 最高只能达到 {overall.finalScore:.1f}。"
                f"建议优先查看相关异常时间段，确认数据是否满足训练使用要求。"
            )
        return (
            f"本段数据需要关注，数据完整性指标低于 {5.0} 阈值，"
            f"触发截断规则，Q_motion 最高只能达到 {overall.finalScore:.1f}。"
        )

    # 场景 C：没有截断，但存在低分运动质量问题
    if facts.topIssues:
        top = facts.topIssues[0]
        return (
            f"本段数据未触发数据完整性截断，但{top.metricId}「{top.name}」"
            f"得分 {top.score:.1f}，存在明显质量问题。"
            f"建议质检员结合曲线和视频重点查看对应异常时间段。"
        )

    # 场景 D：所有指标正常
    return (
        f"本段数据整体质量良好（Q_motion {overall.finalScore:.1f} 分），"
        f"未发现明显的数据完整性、运动质量或学习质量异常。"
        f"各项指标表现稳定，可按常规流程进行人工复核。"
    )
