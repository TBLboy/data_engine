"""AI QC Explain 测试样例。

覆盖 5 类场景：
1. DI-02 = 1.6，触发 3.0 封顶
2. DI-01 = 4.2，触发 6.0 封顶
3. MQ-01 低分，但没有 DI 截断
4. 所有指标良好
5. LLM 不可用时 fallback 正常返回
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from app.ai_qc.facts_builder import build_qc_facts
from app.ai_qc.schemas import AiExplainRequest, QcMetricInput, QcTimelineSegmentInput
from app.ai_qc.template_renderer import render_template
from app.ai_qc.service import AiQcService


def _metric(metricId: str, name: str, dimension: str, score: float, level: str,
            description: str = "") -> QcMetricInput:
    return QcMetricInput(
        metricId=metricId, name=name, qualityDimension=dimension,
        value=score, valueText=f"{score:.1f} 分", score=score, level=level,
        description=description,
    )


def _segment(start: float, end: float, level: str, label: str, metricId: str) -> QcTimelineSegmentInput:
    return QcTimelineSegmentInput(
        start=start, end=end, startSec=start, endSec=end,
        level=level, label=label, sourceMetricId=metricId,
    )


# ── 场景 1：DI-02 = 1.6，触发 3.0 封顶 ──

def test_di_cap_strict():
    req = AiExplainRequest(
        episodeId="test_001",
        qMotionScore=3.0,
        qMotionLevel="bad",
        weightedScoreBeforeCap=7.7,
        metrics=[
            _metric("MQ-01", "平滑度", "motion_quality", 8.5, "good"),
            _metric("MQ-02", "动作饱和", "motion_quality", 9.0, "good"),
            _metric("LQ-01", "动作密度", "learning_quality", 8.0, "good"),
            _metric("DI-01", "时间戳规则性", "data_integrity", 8.0, "good"),
            _metric("DI-02", "传感器同步", "data_integrity", 1.6, "bad",
                    "第 8-15 秒深度相机与关节数据时间戳不同步"),
        ],
        timelineSegments=[
            _segment(8, 15, "bad", "同步异常", "DI-02"),
        ],
    )
    facts = build_qc_facts(req)
    assert facts.overall.capTriggered, "应触发封顶"
    assert len(facts.topIssues) >= 1, "应有 top issue"
    assert facts.topIssues[0].metricId == "DI-02", "DI-02 应为第一 issue"

    text = render_template(facts)
    assert "封顶" in text or "截断" in text, "应包含封顶说明"
    assert "1.6" in text, "应包含 DI-02 分数"
    print("  [PASS] test_di_cap_strict")


# ── 场景 2：DI-01 = 4.2，触发 6.0 封顶 ──

def test_di_cap_moderate():
    req = AiExplainRequest(
        episodeId="test_002",
        qMotionScore=6.0,
        qMotionLevel="warn",
        weightedScoreBeforeCap=8.0,
        metrics=[
            _metric("MQ-01", "平滑度", "motion_quality", 9.0, "good"),
            _metric("LQ-01", "动作密度", "learning_quality", 8.5, "good"),
            _metric("DI-01", "时间戳规则性", "data_integrity", 4.2, "warn",
                    "存在丢帧"),
        ],
        timelineSegments=[
            _segment(3, 5, "warn", "丢帧", "DI-01"),
        ],
    )
    facts = build_qc_facts(req)
    assert facts.overall.capTriggered, "应触发封顶"
    assert facts.overall.finalScore == 6.0

    text = render_template(facts)
    assert "封顶" in text or "截断" in text or "最高只能达到" in text
    print("  [PASS] test_di_cap_moderate")


# ── 场景 3：MQ-01 低分，但没有 DI 截断 ──

def test_mq_low_no_cap():
    req = AiExplainRequest(
        episodeId="test_003",
        qMotionScore=7.0,
        qMotionLevel="warn",
        weightedScoreBeforeCap=None,
        metrics=[
            _metric("MQ-01", "平滑度", "motion_quality", 3.5, "warn",
                    "关节运动存在明显抖动"),
            _metric("DI-01", "时间戳规则性", "data_integrity", 9.0, "good"),
            _metric("DI-02", "传感器同步", "data_integrity", 9.0, "good"),
        ],
    )
    facts = build_qc_facts(req)
    assert not facts.overall.capTriggered, "不应触发截断"
    assert len(facts.topIssues) >= 1

    text = render_template(facts)
    assert "未触发" in text or "平滑度" in text
    print("  [PASS] test_mq_low_no_cap")


# ── 场景 4：所有指标良好 ──

def test_all_good():
    req = AiExplainRequest(
        episodeId="test_004",
        qMotionScore=9.0,
        qMotionLevel="good",
        metrics=[
            _metric("MQ-01", "平滑度", "motion_quality", 9.0, "good"),
            _metric("DI-01", "时间戳规则性", "data_integrity", 9.0, "good"),
        ],
    )
    facts = build_qc_facts(req)
    assert not facts.overall.capTriggered
    assert len(facts.topIssues) == 0

    text = render_template(facts)
    assert "良好" in text or "正常" in text
    print("  [PASS] test_all_good")


# ── 场景 5：LLM 不可用时 fallback ──

def test_llm_unavailable_fallback():
    svc = AiQcService(enabled=True, ollama_base_url="http://127.0.0.1:19999",
                      ollama_model="qwen2.5:7b", timeout_seconds=2)
    req = AiExplainRequest(
        episodeId="test_005",
        qMotionScore=8.0,
        qMotionLevel="good",
        metrics=[
            _metric("MQ-01", "平滑度", "motion_quality", 8.0, "good"),
        ],
    )
    resp = svc.explain(req)
    assert resp.fallbackUsed, "LLM 不可用时应 fallback"
    assert resp.source == "template", "fallback 时应走 template"
    assert resp.explanation, "应有解释文本"
    print("  [PASS] test_llm_unavailable_fallback")


# ── 场景 6：LLM 未启用时不调用 ──

def test_disabled_returns_template():
    svc = AiQcService(enabled=False)
    req = AiExplainRequest(
        episodeId="test_006",
        qMotionScore=8.0,
        qMotionLevel="good",
        metrics=[
            _metric("MQ-01", "平滑度", "motion_quality", 8.0, "good"),
        ],
    )
    resp = svc.explain(req)
    assert not resp.enabled
    assert resp.source == "template"
    assert resp.model is None
    assert not resp.fallbackUsed
    print("  [PASS] test_disabled_returns_template")


if __name__ == '__main__':
    print("Running AI QC Explain tests...\n")
    tests = [
        test_di_cap_strict,
        test_di_cap_moderate,
        test_mq_low_no_cap,
        test_all_good,
        test_llm_unavailable_fallback,
        test_disabled_returns_template,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed")
    sys.exit(0 if passed == len(tests) else 1)
