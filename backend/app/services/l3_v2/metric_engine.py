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
        metrics.append(self._timestamp_regularity(timeline))
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
        joint_jerk = self.f.joint_jerk_norm
        p95 = safe_percentile(joint_jerk, 95, 0.0)
        score = clamp(score_inverse(p95, good=0.006, warn=0.018, bad=0.045))
        spike_threshold = max(0.035, safe_percentile(joint_jerk, 98, 0.035))
        timeline.extend(mask_to_segments(
            joint_jerk > spike_threshold,
            self.f.t_rel,
            label='轨迹突变/不平滑',
            level='warn' if score >= 5 else 'bad',
            source_metric_id='MQ-01',
            source_evidence_id='EV-MOTION-SMOOTHNESS',
            quality_dimension='motion_quality',
            raw_values=joint_jerk,
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
            description='机械臂关节位置三阶差分 P95，衡量加速度变化是否突兀。数值越低表示轨迹越平滑。该指标服务训练数据质量，不评价控制器执行精度。',
            weight=0.38,
        )

    def _motion_continuity(self, timeline: list[dict]) -> MetricResult:
        cont = self.f.action_delta2_norm
        p95 = safe_percentile(cont, 95, 0.0)
        score = clamp(score_inverse(p95, good=0.010, warn=0.030, bad=0.080))
        threshold = max(0.06, safe_percentile(cont, 98, 0.0))
        timeline.extend(mask_to_segments(
            cont > threshold,
            self.f.t_rel,
            label='动作指令突变 / Action 不连续',
            level='warn' if score >= 5 else 'bad',
            source_metric_id='MQ-02',
            source_evidence_id='EV-MOTION-CONTINUITY',
            quality_dimension='motion_quality',
            raw_values=cont,
            threshold=threshold,
            confidence=0.8,
        ))
        return MetricResult(
            metricId='MQ-02',
            name='Motion Continuity',
            qualityDimension='motion_quality',
            evidenceId='EV-MOTION-CONTINUITY',
            value=p95,
            valueText=f'{p95:.4f}',
            unit='action-delta2-p95',
            score=score,
            level=level_from_score(score),
            description='Action 二阶差分 P95，衡量遥操作目标动作是否存在突兀跳变。数值越低表示 action label 越连续。不会惩罚稳定、连续的快速动作，只惩罚忽快忽慢或突然跳变的控制指令。',
            weight=0.32,
        )

    def _motion_stability(self, timeline: list[dict]) -> MetricResult:
        osc = self.f.oscillation_strength
        chat = self.f.chatter_strength
        tau_osc = 0.03
        tau_chat = 0.08
        n = osc.size if osc.size else 1
        n_hand = chat.size if chat.size else 1
        r_osc = float(np.mean(osc > tau_osc)) if osc.size else 0.0
        r_chat = float(np.mean(chat > tau_chat)) if chat.size else 0.0
        raw = 0.6 * r_osc + 0.4 * r_chat
        score = clamp(score_inverse(raw, good=0.05, warn=0.15, bad=0.35))
        mask_osc = osc > tau_osc
        mask_chat = chat > tau_chat
        timeline.extend(mask_to_segments(
            mask_osc,
            self.f.t_rel,
            label='Motion Oscillation',
            level='warn' if r_osc < 0.15 else 'bad',
            source_metric_id='MQ-03',
            source_evidence_id='EV-MOTION-STABILITY',
            quality_dimension='motion_quality',
            raw_values=osc,
            threshold=tau_osc,
            confidence=0.75,
        ))
        timeline.extend(mask_to_segments(
            mask_chat,
            self.f.t_rel,
            label='Hand Chatter',
            level='warn' if r_chat < 0.15 else 'bad',
            source_metric_id='MQ-03',
            source_evidence_id='EV-MOTION-STABILITY',
            quality_dimension='motion_quality',
            raw_values=chat,
            threshold=tau_chat,
            confidence=0.75,
        ))
        return MetricResult(
            metricId='MQ-03',
            name='Motion Stability',
            qualityDimension='motion_quality',
            evidenceId='EV-MOTION-STABILITY',
            value=raw,
            valueText=f'{raw * 100:.1f}%',
            unit='oscillation-ratio',
            score=score,
            level=level_from_score(score),
            description='衡量控制信号是否存在持续性反复修正。使用幅度门控的方向反转检测，区分正常精细调整与控制震荡。比例越低表示示范越稳定。',
            weight=0.30,
        )

    def _effective_action_ratio(self, timeline: list[dict]) -> MetricResult:
        arm_delta = self.f.action_delta_arm_norm
        hand_delta = self.f.action_delta_hand_norm

        # Arm: dynamic P20 threshold with absolute floor
        eps_arm = 0.004  # rad, absolute minimum effective action
        tau_arm = max(float(np.nanpercentile(arm_delta, 20)) if arm_delta.size > 1 else eps_arm, eps_arm)
        eff_arm = arm_delta > tau_arm

        # Hand: dynamic P20 threshold with absolute floor
        eps_hand = 3.0 / 255.0  # normalized, absolute minimum
        tau_hand = max(float(np.nanpercentile(hand_delta, 20)) if hand_delta.size > 1 else eps_hand, eps_hand)
        eff_hand = hand_delta > tau_hand

        # OR fusion: either arm or hand active = effective supervision
        effective = eff_arm | eff_hand
        ratio = float(np.mean(effective)) if effective.size else 0.0
        score = clamp(score_ratio(ratio, good=0.50, warn=0.25, bad=0.08))

        # Timeline: mark long low-effective segments
        low_eff_mask = ~effective
        timeline.extend(mask_to_segments(
            low_eff_mask,
            self.f.t_rel,
            label='Low Effective Action',
            level='warn',
            source_metric_id='LQ-01',
            source_evidence_id='EV-LEARN-ACTION-EFFECTIVENESS',
            quality_dimension='learnability',
            min_dur=1.0,
            gap_merge=0.3,
            confidence=0.7,
        ))
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
            description='分离 arm/hand 的有效动作帧占比（OR 融合）。使用 P20 动态阈值 + 绝对最小值门控，避免微小噪声被计为有效训练信号。',
            weight=0.38,
        )

    def _information_density(self) -> MetricResult:
        arm_delta = self.f.action_delta_arm_norm
        hand_delta = self.f.action_delta_hand_norm
        state_arm = self.f.state_delta_arm_norm
        state_hand = self.f.state_delta_hand_norm

        # Effective coverage (same logic as LQ-01)
        eps_arm, eps_hand_val = 0.004, 3.0 / 255.0
        tau_arm = max(float(np.nanpercentile(arm_delta, 20)) if arm_delta.size > 1 else eps_arm, eps_arm)
        tau_hand = max(float(np.nanpercentile(hand_delta, 20)) if hand_delta.size > 1 else eps_hand_val, eps_hand_val)
        effective = (arm_delta > tau_arm) | (hand_delta > tau_hand)
        r_eff = float(np.mean(effective)) if effective.size else 0.0

        # Action intensity: P75 of max(arm, hand) on effective frames only
        action_max = np.maximum(arm_delta, hand_delta)
        i_a = float(np.nanpercentile(action_max[effective], 75)) if effective.any() and action_max[effective].size else 0.0

        # State intensity: P75 of max(arm, hand) on all frames
        state_max = np.maximum(state_arm, state_hand)
        i_q = safe_percentile(state_max, 75, 0.0)

        raw = 0.7 * (r_eff * i_a) + 0.3 * i_q
        score = clamp(score_ratio(raw, good=0.030, warn=0.012, bad=0.003))
        return MetricResult(
            metricId='LQ-02',
            name='Information Density',
            qualityDimension='learnability',
            evidenceId='EV-LEARN-INFORMATION-DENSITY',
            value=raw,
            valueText=f'{raw:.4f}',
            unit='density-index',
            score=score,
            level=level_from_score(score),
            description='Coverage × Intensity 模型：有效覆盖率 × 动作强度 + 状态强度。分离 arm/hand 并用 max 融合，避免静态控制器拉低信息密度估计。',
            weight=0.34,
        )

    def _low_value_segment_ratio(self, timeline: list[dict]) -> MetricResult:
        arm_delta = self.f.action_delta_arm_norm
        hand_delta = self.f.action_delta_hand_norm
        state_arm = self.f.state_delta_arm_norm
        state_hand = self.f.state_delta_hand_norm
        duration = self.f.duration

        # Effective action mask (same logic as LQ-01)
        eps_arm, eps_hand_val = 0.004, 3.0 / 255.0
        tau_arm = max(float(np.nanpercentile(arm_delta, 20)) if arm_delta.size > 1 else eps_arm, eps_arm)
        tau_hand = max(float(np.nanpercentile(hand_delta, 20)) if hand_delta.size > 1 else eps_hand_val, eps_hand_val)
        effective = (arm_delta > tau_arm) | (hand_delta > tau_hand)

        # State low-change threshold
        state_max = np.maximum(state_arm, state_hand)
        tau_q = max(5e-4, float(np.nanpercentile(state_max, 20)) if state_max.size > 1 else 5e-4)

        # Low-value candidate: no effective action AND low state change
        low_value = (~effective) & (state_max <= tau_q)

        # Segment-level: only count segments >= 1.0s
        raw_segs = mask_to_segments(
            low_value, self.f.t_rel,
            label='low_value_candidate', level='warn',
            source_metric_id='LQ-03', source_evidence_id='EV-LEARN-LOW-VALUE-SEGMENT',
            quality_dimension='learnability',
            min_dur=0.0, gap_merge=0.3, confidence=0.75,
        )
        t_low = sum(max(s['endSec'] - s['startSec'], 0.0) for s in raw_segs if (s['endSec'] - s['startSec']) >= 1.0)
        ratio = t_low / duration if duration > 0 else 0.0
        score = clamp(score_inverse(ratio, good=0.18, warn=0.38, bad=0.65))

        # Timeline: only long-duration low-value segments
        timeline.extend(mask_to_segments(
            low_value, self.f.t_rel,
            label='Low-value Segment / 低学习价值片段',
            level='warn' if score >= 5 else 'bad',
            source_metric_id='LQ-03',
            source_evidence_id='EV-LEARN-LOW-VALUE-SEGMENT',
            quality_dimension='learnability',
            min_dur=1.0, gap_merge=0.3,
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
            description='长持续时间低学习价值片段占比（≥1.0s）。复用 LQ-01 有效动作判定，仅惩罚持续性无监督信号区间，不惩罚短暂停顿。',
            weight=0.28,
        )

    def _timestamp_regularity(self, timeline: list[dict]) -> MetricResult:
        dt = self.f.dt
        n_dt = dt.size
        if n_dt == 0:
            return MetricResult(
                metricId='DI-01', name='Timestamp Regularity', qualityDimension='data_integrity',
                evidenceId='EV-DATA-TIMESTAMP', value=1.0, valueText='1.0000', unit='index',
                score=0.0, level='bad',
                description='无有效时间戳数据。', weight=0.45,
            )
        valid_dt = dt[dt > 0]
        r_invalid = 1.0 - valid_dt.size / max(n_dt, 1)
        dt_med = float(np.median(valid_dt)) if valid_dt.size else 1.0
        jitter = np.abs(dt - dt_med) / (dt_med + 1e-6)
        j_95 = float(np.nanpercentile(jitter, 95)) if jitter.size else 0.0
        r_gap = float(np.mean(dt > 2.0 * dt_med)) if dt.size else 0.0
        raw = 0.5 * j_95 + 0.3 * r_gap + 0.2 * r_invalid
        score = clamp(score_inverse(raw, good=0.05, warn=0.15, bad=0.35))
        mask_invalid = dt <= 0
        mask_gap = dt > 2.0 * dt_med
        timeline.extend(mask_to_segments(
            mask_invalid, self.f.t_rel,
            label='Invalid Timestamp / 非单调时间戳',
            level='bad', source_metric_id='DI-01', source_evidence_id='EV-DATA-TIMESTAMP',
            quality_dimension='data_integrity', min_dur=0.0, gap_merge=0.1, confidence=0.9,
        ))
        timeline.extend(mask_to_segments(
            mask_gap, self.f.t_rel,
            label='Timestamp Gap / 疑似丢帧',
            level='warn', source_metric_id='DI-01', source_evidence_id='EV-DATA-TIMESTAMP',
            quality_dimension='data_integrity', min_dur=0.0, gap_merge=0.3, confidence=0.85,
        ))
        return MetricResult(
            metricId='DI-01', name='Timestamp Regularity', qualityDimension='data_integrity',
            evidenceId='EV-DATA-TIMESTAMP', value=raw, valueText=f'{raw:.4f}', unit='index',
            score=score, level=level_from_score(score),
            description='鲁棒时间戳规则性：J_95(dt偏离中位数) + R_gap(长间隔比例) + R_invalid(非单调比例)。保留 dt CV 为诊断参考。',
            weight=0.45,
        )

    def _sync_validity(self, timeline: list[dict]) -> MetricResult:
        valid = self.f.sync_valid
        diff = self.f.sync_diff_sec
        dt = self.f.dt
        n = valid.size

        if n == 0:
            return MetricResult(
                metricId='DI-02', name='Sensor Synchronization Validity', qualityDimension='data_integrity',
                evidenceId='EV-DATA-SYNC', value=1.0, valueText='100.0%', unit='index',
                score=0.0, level='bad',
                description='无有效同步数据。', weight=0.55,
            )

        valid_dt = dt[dt > 0]
        dt_med = float(np.median(valid_dt)) if valid_dt.size else 0.05
        tau_warn = max(0.05, 2.0 * dt_med)
        tau_bad = max(0.20, 6.0 * dt_med)

        r_flag = float(np.mean(~valid)) if n else 0.0
        r_soft = float(np.mean(diff > tau_warn))
        r_hard = float(np.mean(diff > tau_bad))
        m_sync = min(float(np.nanpercentile(diff, 95)) / max(tau_bad, 1e-6), 1.0) if diff.size else 0.0

        anomaly = (~valid) | (diff > tau_warn)
        raw_segs = mask_to_segments(
            anomaly, self.f.t_rel,
            label='sync_anomaly_candidate', level='warn',
            source_metric_id='DI-02', source_evidence_id='EV-DATA-SYNC',
            quality_dimension='data_integrity', min_dur=0.0, gap_merge=0.3, confidence=0.9,
        )
        t_total = self.f.duration
        t_seg = sum(max(s['endSec'] - s['startSec'], 0.0) for s in raw_segs if (s['endSec'] - s['startSec']) >= 0.5)
        r_seg = t_seg / t_total if t_total > 0 else 0.0

        raw = 0.30 * r_flag + 0.25 * r_hard + 0.20 * r_soft + 0.15 * m_sync + 0.10 * r_seg
        score = clamp(score_inverse(raw, good=0.06, warn=0.15, bad=0.35))

        timeline.extend(mask_to_segments(
            diff > tau_warn, self.f.t_rel,
            label='Sensor Sync Warning / 同步偏差',
            level='warn', source_metric_id='DI-02', source_evidence_id='EV-DATA-SYNC',
            quality_dimension='data_integrity', min_dur=0.5, gap_merge=0.3,
            raw_values=diff, threshold=tau_warn, confidence=0.9,
        ))
        severe = (~valid) | (diff > tau_bad)
        timeline.extend(mask_to_segments(
            severe, self.f.t_rel,
            label='Severe Desync / 严重同步错位',
            level='bad', source_metric_id='DI-02', source_evidence_id='EV-DATA-SYNC',
            quality_dimension='data_integrity', min_dur=0.5, gap_merge=0.3,
            raw_values=diff, threshold=tau_bad, confidence=0.9,
        ))
        return MetricResult(
            metricId='DI-02', name='Sensor Synchronization Validity', qualityDimension='data_integrity',
            evidenceId='EV-DATA-SYNC', value=raw, valueText=f'{raw * 100:.1f}%', unit='index',
            score=score, level=level_from_score(score),
            description='自适应同步有效性：R_flag+R_hard+R_soft+M_sync+R_seg。使用 dt_median 自适应阈值替代固定 700ms，区分轻微偏差与严重错位。',
            weight=0.55,
        )

    def _command_tracking_error(self, timeline: list[dict]) -> MetricResult:
        err = self.f.tracking_error_weighted
        if err.size == 0:
            return MetricResult(
                metricId='DX-01', name='Execution Tracking Diagnostic', qualityDimension='execution_diagnostics',
                evidenceId='EV-DIAG-EXECUTION-TRACKING', value=1.0, valueText='1.000', unit='severity',
                score=0.0, level='bad', description='无有效tracking数据。', confidence=0.8, weight=0.0,
            )
        # Lag alignment: find best k in [0, min(5, N//10)] minimizing P50 error
        N = err.size
        max_lag = min(5, N // 10)
        best_k, best_median = 0, float(np.nanmedian(err)) if err.size else 0.0
        for k in range(1, max_lag + 1):
            aligned = np.abs(err[k:] - err[:-k]) if k < N else err
            med = float(np.nanmedian(err[k:])) if err[k:].size else float('inf')
            if med < best_median:
                best_median, best_k = med, k
        err_aligned = err[best_k:] if best_k > 0 and err.size > best_k else err

        e_mean = safe_mean(err_aligned, 0.0)
        e_p95 = safe_percentile(err_aligned, 95, 0.0)
        tau_warn, tau_bad = 0.20, 0.35
        r_persist = float(np.mean(err_aligned > tau_warn)) if err_aligned.size else 0.0

        severity = clamp(
            0.5 * min(e_p95 / max(tau_bad, 1e-6), 1.0) +
            0.3 * min(e_mean / max(tau_warn, 1e-6), 1.0) +
            0.2 * r_persist
        )
        score = clamp(10.0 * (1.0 - severity))
        level = 'bad' if score < 3.0 else ('warn' if score < 5.0 else 'good')

        timeline.extend(mask_to_segments(
            err_aligned > tau_warn, self.f.t_rel[best_k:] if best_k > 0 else self.f.t_rel,
            label='Execution Tracking Error / 执行跟踪偏差',
            level='warn', source_metric_id='DX-01', source_evidence_id='EV-DIAG-EXECUTION-TRACKING',
            quality_dimension='execution_diagnostics', min_dur=0.5, gap_merge=0.3,
            raw_values=err_aligned, threshold=tau_warn, confidence=0.8,
        ))
        timeline.extend(mask_to_segments(
            err_aligned > tau_bad, self.f.t_rel[best_k:] if best_k > 0 else self.f.t_rel,
            label='Severe Tracking Error / 严重跟踪偏差',
            level='bad', source_metric_id='DX-01', source_evidence_id='EV-DIAG-EXECUTION-TRACKING',
            quality_dimension='execution_diagnostics', min_dur=0.5, gap_merge=0.3,
            raw_values=err_aligned, threshold=tau_bad, confidence=0.8,
        ))
        return MetricResult(
            metricId='DX-01', name='Execution Tracking Diagnostic', qualityDimension='execution_diagnostics',
            evidenceId='EV-DIAG-EXECUTION-TRACKING', value=severity, valueText=f'{severity:.3f}', unit='severity',
            score=score, level=level,
            description=f'执行链路跟踪诊断（lag={best_k}frames）。Arm 0.7 + Hand 0.3 加权 RMS 误差，使用 lag alignment 对齐。不参与训练质量总分。',
            confidence=0.8, weight=0.0,
        )
