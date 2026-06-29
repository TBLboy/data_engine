from __future__ import annotations

from collections import defaultdict
from typing import Any

from .metric_engine import MetricResult
from .utils import level_from_score, weighted_average, clamp


DIMENSION_META = {
    'motion_quality': {
        'label': 'Motion Quality', 'labelZh': '动作示范质量', 'weight': 0.40,
        'summary': '评估示范轨迹是否平滑、连续、稳定，关注模型会不会学到抖动、跳变和反复修正。',
    },
    'learnability': {
        'label': 'Learnability', 'labelZh': '可学习性', 'weight': 0.40,
        'summary': '评估该 episode 是否包含足够有效的 observation-action 学习信号。',
    },
    'data_integrity': {
        'label': 'Data Integrity', 'labelZh': '数据完整性', 'weight': 0.20,
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
    """Quality fusion layer with soft-min penalties and Data Integrity cap."""

    def __init__(self, metrics: list[MetricResult], diagnostics: list[MetricResult], params: dict[str, Any] | None = None):
        self.metrics = metrics
        self.diagnostics = diagnostics
        self.p = params or {}

    def _level(self, score: float) -> str:
        return level_from_score(score, good=self.p.get('sl_level_good', 7.5), warn=self.p.get('sl_level_warn', 5.0))

    def build_report(self) -> dict:
        dimension_groups: dict[str, list[MetricResult]] = defaultdict(list)
        for metric in self.metrics:
            dimension_groups[metric.qualityDimension].append(metric)

        dimensions: list[dict] = []
        for dim_id, meta in DIMENSION_META.items():
            dim_metrics = dimension_groups.get(dim_id, [])
            evidence_groups = self._build_evidence_groups(dim_id, dim_metrics)
            dim_score = self._dimension_score(dim_id, dim_metrics, evidence_groups)
            dimensions.append({
                'dimensionId': dim_id,
                'label': meta['label'],
                'labelZh': meta['labelZh'],
                'score': round(dim_score, 2),
                'level': self._level(dim_score),
                'weight': meta['weight'],
                'summary': meta['summary'],
                'evidenceGroups': evidence_groups,
            })

        dim_map = {d['dimensionId']: d['score'] for d in dimensions}
        s_motion = dim_map.get('motion_quality', 5.0)
        s_learn = dim_map.get('learnability', 5.0)
        s_data = dim_map.get('data_integrity', 5.0)

        w_motion = self.p.get('qf_motion_weight', 0.40)
        w_learn = self.p.get('qf_learn_weight', 0.40)
        w_data = self.p.get('qf_data_weight', 0.20)
        weighted = w_motion * s_motion + w_learn * s_learn + w_data * s_data

        if s_data < self.p.get('qf_data_cap_strict_threshold', 3.0):
            total = min(weighted, self.p.get('qf_data_cap_strict', 4.5))
        elif s_data < self.p.get('qf_data_cap_moderate_threshold', 5.0):
            total = min(weighted, self.p.get('qf_data_cap_moderate', 6.0))
        else:
            total = weighted

        reliability_warnings = []
        di_vals = {m.metricId: m for m in self.metrics if m.qualityDimension == 'data_integrity'}
        if di_vals.get('DI-02') and di_vals['DI-02'].level == 'bad':
            reliability_warnings.append('严重同步异常，运动与学习价值指标可信度下降')
        if di_vals.get('DI-01') and di_vals['DI-01'].level == 'bad':
            reliability_warnings.append('时间戳严重异常，时序指标可信度下降')
        if s_data < 5.0:
            reliability_warnings.append('Data Integrity 评分低于 5.0，Training Quality Score 已触发上限封顶')
        if s_data < 3.0:
            reliability_warnings.append('Data Integrity 评分低于 3.0，Training Quality Score 已触发严格上限封顶')

        diag_warnings = []
        diag_map = {m.metricId: m for m in self.diagnostics}
        if diag_map.get('DX-01') and diag_map['DX-01'].score < 5.0:
            diag_warnings.append('执行跟踪偏差较大，建议检查控制器或遥操作链路')

        return {
            'version': 'RDDQF-L3-v2-MVP',
            'trainingQualityScore': round(total, 2),
            'trainingQualityLevel': self._level(total),
            'scoreLabel': 'Training Quality',
            'qualityDimensions': dimensions,
            'metricResults': [m.to_dict() for m in self.metrics],
            'diagnosticMetrics': [m.to_dict() for m in self.diagnostics],
            'reliabilityWarnings': reliability_warnings,
            'diagnosticWarnings': diag_warnings,
            'summary': self._summary(total, dimensions, reliability_warnings),
        }

    def _dimension_score(self, dim_id: str, metrics: list[MetricResult], evidence_groups: list[dict]) -> float:
        if not metrics:
            return 5.0
        scores = [m.score for m in metrics]
        mean_score = sum(scores) / len(scores)
        if dim_id == 'data_integrity':
            return self.p.get('qf_data_softmin_ratio', 0.4) * min(scores) + (1.0 - self.p.get('qf_data_softmin_ratio', 0.4)) * mean_score
        if dim_id == 'motion_quality':
            r = self.p.get('qf_motion_softmin_ratio', 0.2)
        else:
            r = self.p.get('qf_learn_softmin_ratio', 0.2)
        return (1.0 - r) * mean_score + r * min(scores)

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
                'level': self._level(score),
                'confidence': round(min((m.confidence for m in items), default=1.0), 3),
                'summary': summary,
                'metrics': [m.to_dict() for m in items],
                'weight': round(sum(m.weight for m in items) / max(len(items), 1), 3),
            })
        return sorted(out, key=lambda x: x['score'])

    @staticmethod
    def _summary(total: float, dimensions: list[dict], warnings: list[str]) -> str:
        weakest = min(dimensions, key=lambda x: x['score'], default=None)
        base = ''
        if weakest is None:
            base = '未获得足够数据计算 L3 v2 训练质量。'
        elif total >= 7.5:
            base = f'该 episode 的训练数据质量较好，当前主要短板为：{weakest["labelZh"]}。'
        elif total >= 5.0:
            base = f'该 episode 可作为候选训练数据，但建议重点核查：{weakest["labelZh"]}。'
        else:
            base = f'该 episode 训练数据质量风险较高，优先核查：{weakest["labelZh"]}。'
        if warnings:
            base += ' ' + '；'.join(warnings[:2])
        return base
