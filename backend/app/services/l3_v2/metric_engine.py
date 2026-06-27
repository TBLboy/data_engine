from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .feature_extractor import L3V2Features
from .utils import clamp, level_from_score, mask_to_segments, safe_mean, safe_percentile, score_inverse, score_ratio


@dataclass
class MetricResult:
    metricId: str
    name: str
    qualityDimension: str
    evidenceId: str
    value: float
    valueText: str
    unit: str
    score: float
    level: str
    description: str
    confidence: float = 1.0
    weight: float = 1.0

    def to_dict(self) -> dict:
        return {
            'metricId': self.metricId,
            'name': self.name,
            'qualityDimension': self.qualityDimension,
            'evidenceId': self.evidenceId,
            'value': round(float(self.value), 6),
            'valueText': self.valueText,
            'unit': self.unit,
            'score': round(float(self.score), 2),
            'level': self.level,
            'description': self.description,
            'confidence': round(float(self.confidence), 3),
            'weight': round(float(self.weight), 3),
        }


class MetricEngine:
    """Metric layer for RDDQF-L3 v2 MVP.

    The MVP intentionally uses metrics that can be computed from current
    TeleDex telemetry.npz, without requiring task-level VLM or tactile models.
    """

    def __init__(self, features: L3V2Features):
        self.f = features

    def compute(self) -> tuple[list[MetricResult], list[dict], list[MetricResult]]:
        metrics: list[MetricResult] = []
        diagnostics: list[MetricResult] = []
        timeline: list[dict] = []

        metrics.append(self._trajectory_smoothness(timeline))
        metrics.append(self._motion_continuity(timeline))
        metrics.append(self._motion_stability(timeline))
        metrics.append(self._effective_action_ratio(timeline))
        metrics.append(self._information_density())
        metrics.append(self._low_value_segment_ratio(timeline))
        metrics.append(self._timestamp_regularity())
        metrics.append(self._sync_validity(timeline))
        diagnostics.append(self._command_tracking_error(timeline))

        if not timeline:
            end = round(float(self.f.duration), 3)
            timeline.append({
                'start': 0.0,
                'end': end,
                'startSec': 0.0,
                'endSec': end,
                'level': 'good',
                'label': '全段无显著 L3 v2 异常',
                'sourceMetricId': 'l3v2.overall',
                'sourceEvidenceId': 'overall.normal',
                'qualityDimension': 'overall',
                'rawValue': None,
                'threshold': None,
                'confidence': 0.8,
            })

        return metrics, sorted(timeline, key=lambda x: (x.get('startSec', 0), x.get('sourceMetricId', ''))), diagnostics

    def _trajectory_smoothness(self, timeline: list[dict]) -> MetricResult:
        jerk = self.f.joint_jerk_norm
        p95 = safe_percentile(jerk, 95, 0.0)
        # Joint jerk from second-order differences is dimensionless in this aligned frame domain.
        score = clamp(score_inverse(p95, good=0.015, warn=0.04, bad=0.08))
        spike_threshold = max(0.06, safe_percentile(jerk, 98, 0.06))
        timeline.extend(mask_to_segments(
            jerk > spike_threshold,
            self.f.t_rel,
            label='轨迹突变/不平滑',
            level='warn' if score >= 5 else 'bad',
            source_metric_id='MQ-01',
            source_evidence_id='EV-MOTION-SMOOTHNESS',
            quality_dimension='motion_quality',
            raw_values=jerk,
            threshold=spike_threshold,
            confidence=0.85,
        ))
        return MetricResult(
            metricId='MQ-01',
            name='Trajectory Smoothness',
            qualityDimension='motion_quality',
            evidenceId='EV-MOTION-SMOOTHNESS',
            value=p95,
            valueText=f'{p95:.4f}',
            unit='joint-jerk-p95',
            score=score,
            level=level_from_score(score),
            description='基于关节轨迹二阶差分的 P95 平滑度证据。该指标服务训练数据质量，不评价控制器执行精度。',
            weight=0.38,
        )

    def _motion_continuity(self, timeline: list[dict]) -> MetricResult:
        strength = self.f.action_discontinuity_strength
        ratio = float(np.mean(strength > 1.5)) if strength.size else 0.0
        score = clamp(score_inverse(ratio, good=0.03, warn=0.10, bad=0.25))
        timeline.extend(mask_to_segments(
            strength > 2.0,
            self.f.t_rel,
            label='动作不连续/跳变',
            level='warn' if score >= 5 else 'bad',
            source_metric_id='MQ-02',
            source_evidence_id='EV-MOTION-CONTINUITY',
            quality_dimension='motion_quality',
            raw_values=strength,
            threshold=2.0,
            confidence=0.8,
        ))
        return MetricResult(
            metricId='MQ-02',
            name='Motion Continuity',
            qualityDimension='motion_quality',
            evidenceId='EV-MOTION-CONTINUITY',
            value=ratio,
            valueText=f'{ratio * 100:.1f}%',
            unit='ratio',
            score=score,
            level=level_from_score(score),
            description='检测 action 序列中相对自身分布过大的跳变比例。对训练数据而言，突兀 label 会降低可学习性。',
            weight=0.32,
        )

    def _motion_stability(self, timeline: list[dict]) -> MetricResult:
        reversal_p95 = safe_percentile(self.f.reversal_rate_per_frame, 95, 0.0)
        hand_chatter_p95 = safe_percentile(self.f.hand_chatter_strength, 95, 0.0)
        instability = 0.65 * reversal_p95 + 0.35 * hand_chatter_p95
        score = clamp(score_inverse(instability, good=0.08, warn=0.20, bad=0.45))
        mask = (self.f.reversal_rate_per_frame > 0.35) | (self.f.hand_chatter_strength > 0.35)
        timeline.extend(mask_to_segments(
            mask,
            self.f.t_rel,
            label='动作反复/手部颤振',
            level='warn' if score >= 5 else 'bad',
            source_metric_id='MQ-03',
            source_evidence_id='EV-MOTION-STABILITY',
            quality_dimension='motion_quality',
            raw_values=0.65 * self.f.reversal_rate_per_frame + 0.35 * self.f.hand_chatter_strength,
            threshold=0.35,
            confidence=0.75,
        ))
        return MetricResult(
            metricId='MQ-03',
            name='Motion Stability',
            qualityDimension='motion_quality',
            evidenceId='EV-MOTION-STABILITY',
            value=instability,
            valueText=f'{instability:.3f}',
            unit='instability-index',
            score=score,
            level=level_from_score(score),
            description='综合方向反转和手部颤振证据，识别示范中的犹豫、反复修正和高频不稳定。',
            weight=0.30,
        )

    def _effective_action_ratio(self, timeline: list[dict]) -> MetricResult:
        delta = self.f.joint_action_delta_norm
        if delta.size <= 1:
            ratio = 0.0
            threshold = 0.0
        else:
            threshold = max(float(np.nanpercentile(delta, 35)), 1e-4)
            ratio = float(np.mean(delta > threshold))
        score = clamp(score_ratio(ratio, good=0.50, warn=0.25, bad=0.08))
        return MetricResult(
            metricId='LQ-01',
            name='Effective Action Ratio',
            qualityDimension='learnability',
            evidenceId='EV-LEARN-ACTION-EFFECTIVENESS',
            value=ratio,
            valueText=f'{ratio * 100:.1f}%',
            unit='ratio',
            score=score,
            level=level_from_score(score),
            description='估计 episode 中包含有效 action 变化的帧比例。它衡量训练 label 的有效密度，而不是动作绝对幅值。',
            weight=0.38,
        )

    def _information_density(self) -> MetricResult:
        action_var = safe_percentile(self.f.joint_action_delta_norm, 75, 0.0)
        state_var = safe_percentile(self.f.joint_state_delta_norm, 75, 0.0)
        raw = 0.6 * action_var + 0.4 * state_var
        score = clamp(score_ratio(raw, good=0.045, warn=0.018, bad=0.004))
        return MetricResult(
            metricId='LQ-02',
            name='Information Density',
            qualityDimension='learnability',
            evidenceId='EV-LEARN-INFORMATION-DENSITY',
            value=raw,
            valueText=f'{raw:.4f}',
            unit='delta-index',
            score=score,
            level=level_from_score(score),
            description='用 action 变化和状态变化的分位统计估计学习信号密度，避免把长时间低变化片段误当成高价值数据。',
            weight=0.34,
        )

    def _low_value_segment_ratio(self, timeline: list[dict]) -> MetricResult:
        mask = self.f.low_change_mask
        ratio = float(np.mean(mask)) if mask.size else 0.0
        score = clamp(score_inverse(ratio, good=0.18, warn=0.38, bad=0.65))
        timeline.extend(mask_to_segments(
            mask,
            self.f.t_rel,
            label='低学习价值片段',
            level='warn' if score >= 5 else 'bad',
            source_metric_id='LQ-03',
            source_evidence_id='EV-LEARN-LOW-VALUE-SEGMENT',
            quality_dimension='learnability',
            threshold=0.0,
            confidence=0.75,
        ))
        return MetricResult(
            metricId='LQ-03',
            name='Low-value Segment Ratio',
            qualityDimension='learnability',
            evidenceId='EV-LEARN-LOW-VALUE-SEGMENT',
            value=ratio,
            valueText=f'{ratio * 100:.1f}%',
            unit='ratio',
            score=score,
            level=level_from_score(score),
            description='检测 action 和 qpos 同时低变化的片段比例。该指标关注训练样本是否携带足够学习信号。',
            weight=0.28,
        )

    def _timestamp_regularity(self) -> MetricResult:
        cv = self.f.timestamp_jitter_cv
        score = clamp(score_inverse(cv, good=0.02, warn=0.05, bad=0.12))
        return MetricResult(
            metricId='DI-01',
            name='Timestamp Regularity',
            qualityDimension='data_integrity',
            evidenceId='EV-DATA-TIMESTAMP',
            value=cv,
            valueText=f'{cv:.4f}',
            unit='cv',
            score=score,
            level=level_from_score(score),
            description='采样时间间隔变异系数。时间轴越稳定，下游序列模型越容易获得可靠的时序监督。',
            weight=0.45,
        )

    def _sync_validity(self, timeline: list[dict]) -> MetricResult:
        mask = self.f.sync_bad_mask
        bad_ratio = float(np.mean(mask)) if mask.size else 0.0
        score = clamp(score_inverse(bad_ratio, good=0.01, warn=0.05, bad=0.15))
        timeline.extend(mask_to_segments(
            mask,
            self.f.t_rel,
            label='同步异常',
            level='bad' if bad_ratio > 0.05 else 'warn',
            source_metric_id='DI-02',
            source_evidence_id='EV-DATA-SYNC',
            quality_dimension='data_integrity',
            threshold=700.0,
            confidence=0.9,
        ))
        return MetricResult(
            metricId='DI-02',
            name='Sensor Synchronization Validity',
            qualityDimension='data_integrity',
            evidenceId='EV-DATA-SYNC',
            value=bad_ratio,
            valueText=f'{bad_ratio * 100:.1f}%',
            unit='ratio',
            score=score,
            level=level_from_score(score),
            description='基于 TeleDex sync_validation 字段评估多模态同步有效性。同步错误会直接破坏 observation-action 对齐。',
            weight=0.55,
        )

    def _command_tracking_error(self, timeline: list[dict]) -> MetricResult:
        tracking = self.f.tracking_error_weighted
        p95 = safe_percentile(tracking, 95, 0.0)
        score = clamp(score_inverse(p95, good=0.12, warn=0.20, bad=0.35))
        timeline.extend(mask_to_segments(
            tracking > 0.20,
            self.f.t_rel,
            label='执行跟踪偏差（诊断）',
            level='warn' if p95 <= 0.35 else 'bad',
            source_metric_id='DX-01',
            source_evidence_id='EV-DIAG-EXECUTION-TRACKING',
            quality_dimension='execution_diagnostics',
            raw_values=tracking,
            threshold=0.20,
            confidence=0.8,
        ))
        return MetricResult(
            metricId='DX-01',
            name='Command Tracking Error',
            qualityDimension='execution_diagnostics',
            evidenceId='EV-DIAG-EXECUTION-TRACKING',
            value=p95,
            valueText=f'{p95:.3f}',
            unit='weighted-p95',
            score=score,
            level=level_from_score(score),
            description='目标关节位置与实际关节位置的 P95 误差。L3 v2 中该项仅作为执行诊断，不进入训练质量总分。',
            confidence=0.8,
            weight=0.0,
        )
