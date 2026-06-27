from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict

from .metric_engine import MetricResult
from .utils import level_from_score, weighted_average


DIMENSION_META = {
    'motion_quality': {
        'label': 'Motion Quality',
        'labelZh': '动作示范质量',
        'weight': 0.45,
        'summary': '评估示范轨迹是否平滑、连续、稳定，关注模型会不会学到抖动、跳变和反复修正。',
    },
    'learnability': {
        'label': 'Learnability',
        'labelZh': '可学习性',
        'weight': 0.35,
        'summary': '评估该 episode 是否包含足够有效的 observation-action 学习信号。',
    },
    'data_integrity': {
        'label': 'Data Integrity',
        'labelZh': '数据完整性',
        'weight': 0.20,
        'summary': '评估时间轴和多模态同步是否可靠，决定样本是否适合进入训练集。',
    },
}

EVIDENCE_META = {
    'EV-MOTION-SMOOTHNESS': ('运动平滑性证据', '轨迹是否存在明显 jerk 或突变。'),
    'EV-MOTION-CONTINUITY': ('运动连续性证据', 'action label 是否连续自然。'),
    'EV-MOTION-STABILITY': ('运动稳定性证据', '是否存在反复修正、犹豫或手部颤振。'),
    'EV-LEARN-ACTION-EFFECTIVENESS': ('有效动作证据', 'episode 中有效 action 变化的密度。'),
    'EV-LEARN-INFORMATION-DENSITY': ('信息密度证据', '状态和动作变化是否为模型提供足够监督信号。'),
    'EV-LEARN-LOW-VALUE-SEGMENT': ('低价值片段证据', '长时间低变化片段会稀释训练价值。'),
    'EV-DATA-TIMESTAMP': ('时间轴证据', '时间戳是否规则。'),
    'EV-DATA-SYNC': ('同步证据', '多模态数据是否对齐。'),
}


class QualityEngine:
    """Quality fusion layer: metric -> evidence -> quality dimension -> total score."""

    def __init__(self, metrics: list[MetricResult], diagnostics: list[MetricResult]):
        self.metrics = metrics
        self.diagnostics = diagnostics

    def build_report(self) -> dict:
        dimension_groups: dict[str, list[MetricResult]] = defaultdict(list)
        for metric in self.metrics:
            dimension_groups[metric.qualityDimension].append(metric)

        dimensions: list[dict] = []
        for dim_id, meta in DIMENSION_META.items():
            dim_metrics = dimension_groups.get(dim_id, [])
            evidence_groups = self._build_evidence_groups(dim_id, dim_metrics)
            score = weighted_average((item['score'], item.get('weight', 1.0)) for item in evidence_groups)
            dimensions.append({
                'dimensionId': dim_id,
                'label': meta['label'],
                'labelZh': meta['labelZh'],
                'score': round(score, 2),
                'level': level_from_score(score),
                'weight': meta['weight'],
                'summary': meta['summary'],
                'evidenceGroups': evidence_groups,
            })

        total = weighted_average((d['score'], d['weight']) for d in dimensions)
        return {
            'version': 'RDDQF-L3-v2-MVP',
            'trainingQualityScore': round(total, 2),
            'trainingQualityLevel': level_from_score(total),
            'scoreLabel': 'Training Quality',
            'qualityDimensions': dimensions,
            'metricResults': [m.to_dict() for m in self.metrics],
            'diagnosticMetrics': [m.to_dict() for m in self.diagnostics],
            'summary': self._summary(total, dimensions),
        }

    def _build_evidence_groups(self, dim_id: str, metrics: list[MetricResult]) -> list[dict]:
        by_evidence: dict[str, list[MetricResult]] = defaultdict(list)
        for metric in metrics:
            by_evidence[metric.evidenceId].append(metric)
        out: list[dict] = []
        for evidence_id, items in by_evidence.items():
            label, summary = EVIDENCE_META.get(evidence_id, (evidence_id, ''))
            score = weighted_average((m.score, m.weight) for m in items)
            out.append({
                'evidenceId': evidence_id,
                'label': label,
                'qualityDimension': dim_id,
                'score': round(score, 2),
                'level': level_from_score(score),
                'confidence': round(min((m.confidence for m in items), default=1.0), 3),
                'summary': summary,
                'metrics': [m.to_dict() for m in items],
                'weight': round(sum(m.weight for m in items) / max(len(items), 1), 3),
            })
        return sorted(out, key=lambda x: x['score'])

    @staticmethod
    def _summary(total: float, dimensions: list[dict]) -> str:
        weakest = min(dimensions, key=lambda x: x['score'], default=None)
        if weakest is None:
            return '未获得足够数据计算 L3 v2 训练质量。'
        if total >= 7.5:
            return f'该 episode 的训练数据质量较好，当前主要短板为：{weakest["labelZh"]}。'
        if total >= 5.0:
            return f'该 episode 可作为候选训练数据，但建议重点核查：{weakest["labelZh"]}。'
        return f'该 episode 训练数据质量风险较高，优先核查：{weakest["labelZh"]}。'
