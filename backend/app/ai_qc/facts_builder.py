from __future__ import annotations

from app.ai_qc.schemas import (
    AiExplainRequest,
    QcFacts,
    QcIssue,
    QcOverallFacts,
)

# DI 指标封顶阈值（与 L3 v2 quality_engine.py 保持一致）
DI_CAP_STRICT_THRESHOLD = 3.0
DI_CAP_MODERATE_THRESHOLD = 5.0


def build_qc_facts(request: AiExplainRequest) -> QcFacts:
    metrics = sorted(request.metrics, key=lambda m: m.score)
    di_metrics = [m for m in metrics if m.qualityDimension == "data_integrity"]
    worst_di = min((m.score for m in di_metrics), default=10.0)

    # 判断是否触发截断
    cap_triggered = False
    cap_reason = ""
    if worst_di < DI_CAP_STRICT_THRESHOLD:
        cap_triggered = True
        worst_di_metric = next((m for m in di_metrics if m.score == worst_di), None)
        cap_reason = (
            f"{worst_di_metric.metricId}={worst_di_metric.score} < {DI_CAP_STRICT_THRESHOLD}"
            if worst_di_metric
            else f"最差 DI 指标得分 {worst_di} < {DI_CAP_STRICT_THRESHOLD}"
        )
    elif worst_di < DI_CAP_MODERATE_THRESHOLD:
        cap_triggered = True
        worst_di_metric = next((m for m in di_metrics if m.score == worst_di), None)
        cap_reason = (
            f"{worst_di_metric.metricId}={worst_di_metric.score} < {DI_CAP_MODERATE_THRESHOLD}"
            if worst_di_metric
            else f"最差 DI 指标得分 {worst_di} < {DI_CAP_MODERATE_THRESHOLD}"
        )

    # 提取 top issues：score < 5 的指标优先，bad 优先于 warn
    bad_issues = [m for m in metrics if m.level == "bad" and m.score < 5.0]
    warn_issues = [m for m in metrics if m.level == "warn" and m.score < 5.0]
    top_issues: list[QcIssue] = []
    for m in bad_issues + warn_issues:
        evidence = m.description or f"{m.name} 得分 {m.score}"
        # 附加 timeline 中属于该指标的时间段描述
        related_segments = [
            s for s in request.timelineSegments if s.sourceMetricId == m.metricId
        ]
        if related_segments:
            segment_labels = [
                f"第{s.startSec:.0f}-{s.endSec:.0f}秒{s.label}" for s in related_segments[:3]
            ]
            evidence += "（" + "；".join(segment_labels) + "）"
        top_issues.append(
            QcIssue(
                metricId=m.metricId,
                name=m.name,
                score=m.score,
                level=m.level,
                evidence=evidence,
            )
        )
        if len(top_issues) >= 3:
            break

    # 正常证据：score >= 7 的指标
    normal_evidence: list[str] = []
    for m in metrics:
        if m.score >= 7.0:
            normal_evidence.append(f"{m.metricId} {m.name} 正常，{m.score:.1f} 分")
        if len(normal_evidence) >= 4:
            break

    # 审查建议
    suggestion_parts: list[str] = []
    if cap_triggered:
        suggestion_parts.append("数据完整性异常导致 Q_motion 被封顶")
    if top_issues:
        bad_segments = [
            s
            for s in request.timelineSegments
            if any(i.metricId == s.sourceMetricId for i in top_issues)
        ]
        if bad_segments:
            times = sorted({f"第{s.startSec:.0f}-{s.endSec:.0f}秒" for s in bad_segments})
            suggestion_parts.append(f"建议优先查看{'、'.join(times[:3])}的视频和曲线")
    if not suggestion_parts:
        suggestion_parts.append("建议按常规流程进行人工复核")

    return QcFacts(
        overall=QcOverallFacts(
            finalScore=request.qMotionScore,
            weightedScoreBeforeCap=request.weightedScoreBeforeCap,
            level=request.qMotionLevel,
            capTriggered=cap_triggered,
            capReason=cap_reason if cap_triggered else "",
        ),
        topIssues=top_issues,
        normalEvidence=normal_evidence,
        reviewSuggestion="，".join(suggestion_parts),
    )
