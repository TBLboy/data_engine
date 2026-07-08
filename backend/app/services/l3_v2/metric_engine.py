from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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

    def __init__(self, features: L3V2Features, params: dict[str, Any] | None = None):
        self.f = features
        self.p = params or {}

    def _level(self, score: float) -> str:
        return level_from_score(score, good=self.p.get('sl_level_good', 7.5), warn=self.p.get('sl_level_warn', 5.0))

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
        diagnostics.append(self._data_validity())
        metrics.append(self._dimension_health())
        metrics.append(self._episode_completeness())

        if not timeline:
            end = round(float(self.f.duration), 3)
            timeline.append({
                'start': 0.0,
                'end': end,
                'startSec': 0.0,
                'endSec': end,
                'level': 'good',
                'label': '全段无显著异常',
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
        good = self.p.get('mq01_good', 0.006)
        warn = self.p.get('mq01_warn', 0.018)
        bad = self.p.get('mq01_bad', 0.045)
        score = clamp(score_inverse(p95, good=good, warn=warn, bad=bad))
        spike_floor = self.p.get('mq01_spike_p98_floor', 0.035)
        spike_threshold = max(spike_floor, safe_percentile(joint_jerk, 98, spike_floor))
        timeline.extend(mask_to_segments(
            joint_jerk > spike_threshold,
            self.f.t_rel,
            label='轨迹突变',
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
            name='轨迹平滑度',
            qualityDimension='motion_quality',
            evidenceId='EV-MOTION-SMOOTHNESS',
            value=p95,
            valueText=f'{p95:.4f}',
            unit='关节jerk-P95',
            score=score,
            level=self._level(score),
            description='机械臂关节位置三阶差分 P95，衡量加速度变化是否突兀。数值越低表示轨迹越平滑。该指标服务训练数据质量，不评价控制器执行精度。',
            weight=self.p.get('mq01_weight', 0.38),
        )

    def _motion_continuity(self, timeline: list[dict]) -> MetricResult:
        cont = self.f.action_delta2_norm
        p95 = safe_percentile(cont, 95, 0.0)
        good = self.p.get('mq02_good', 0.010)
        warn = self.p.get('mq02_warn', 0.030)
        bad = self.p.get('mq02_bad', 0.080)
        score = clamp(score_inverse(p95, good=good, warn=warn, bad=bad))
        threshold_floor = self.p.get('mq02_threshold_floor', 0.06)
        threshold = max(threshold_floor, safe_percentile(cont, 98, 0.0))
        timeline.extend(mask_to_segments(
            cont > threshold,
            self.f.t_rel,
            label='动作指令突变',
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
            name='动作连续性',
            qualityDimension='motion_quality',
            evidenceId='EV-MOTION-CONTINUITY',
            value=p95,
            valueText=f'{p95:.4f}',
            unit='动作二阶差分-P95',
            score=score,
            level=self._level(score),
            description='Action 二阶差分 P95，衡量遥操作目标动作是否存在突兀跳变。数值越低表示 action label 越连续。不会惩罚稳定、连续的快速动作，只惩罚忽快忽慢或突然跳变的控制指令。',
            weight=self.p.get('mq02_weight', 0.32),
        )

    def _motion_stability(self, timeline: list[dict]) -> MetricResult:
        osc = self.f.oscillation_strength
        chat = self.f.chatter_strength
        tau_osc = self.p.get('mq03_osc_threshold', 0.03)
        tau_chat = self.p.get('mq03_chat_threshold', 0.08)
        r_osc = float(np.mean(osc > tau_osc)) if osc.size else 0.0
        r_chat = float(np.mean(chat > tau_chat)) if chat.size else 0.0
        w_osc = self.p.get('mq03_osc_weight', 0.6)
        w_chat = self.p.get('mq03_chat_weight', 0.4)
        raw = w_osc * r_osc + w_chat * r_chat
        good = self.p.get('mq03_good', 0.05)
        warn = self.p.get('mq03_warn', 0.15)
        bad = self.p.get('mq03_bad', 0.35)
        score = clamp(score_inverse(raw, good=good, warn=warn, bad=bad))
        mask_osc = osc > tau_osc
        mask_chat = chat > tau_chat
        timeline.extend(mask_to_segments(
            mask_osc,
            self.f.t_rel,
            label='运动震荡',
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
            label='手指颤振',
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
            name='运动稳定性',
            qualityDimension='motion_quality',
            evidenceId='EV-MOTION-STABILITY',
            value=raw,
            valueText=f'{raw * 100:.1f}%',
            unit='震荡比例',
            score=score,
            level=self._level(score),
            description='衡量控制信号是否存在持续性反复修正。使用幅度门控的方向反转检测，区分正常精细调整与控制震荡。比例越低表示示范越稳定。',
            weight=self.p.get('mq03_weight', 0.30),
        )

    def _effective_action_ratio(self, timeline: list[dict]) -> MetricResult:
        arm_delta = self.f.action_delta_arm_norm
        hand_delta = self.f.action_delta_hand_norm

        eps_arm = self.p.get('lq01_eps_arm', 0.004)
        eps_hand = self.p.get('lq01_eps_hand', 3.0 / 255.0)

        tau_arm = max(float(np.nanpercentile(arm_delta, 20)) if arm_delta.size > 1 else eps_arm, eps_arm)
        eff_arm = arm_delta > tau_arm

        tau_hand = max(float(np.nanpercentile(hand_delta, 20)) if hand_delta.size > 1 else eps_hand, eps_hand)
        eff_hand = hand_delta > tau_hand

        effective = eff_arm | eff_hand
        ratio = float(np.mean(effective)) if effective.size else 0.0
        good = self.p.get('lq01_good', 0.50)
        warn = self.p.get('lq01_warn', 0.25)
        bad = self.p.get('lq01_bad', 0.08)
        score = clamp(score_ratio(ratio, good=good, warn=warn, bad=bad))

        low_eff_mask = ~effective
        timeline.extend(mask_to_segments(
            low_eff_mask,
            self.f.t_rel,
            label='低效动作',
            level='warn',
            source_metric_id='LQ-01',
            source_evidence_id='EV-LEARN-ACTION-EFFECTIVENESS',
            quality_dimension='learnability',
            min_dur=self.p.get('lq01_min_dur', 1.0),
            gap_merge=self.p.get('lq01_gap_merge', 0.3),
            confidence=0.7,
        ))
        return MetricResult(
            metricId='LQ-01',
            name='有效动作比',
            qualityDimension='learnability',
            evidenceId='EV-LEARN-ACTION-EFFECTIVENESS',
            value=ratio,
            valueText=f'{ratio * 100:.1f}%',
            unit='比例',
            score=score,
            level=self._level(score),
            description='分离 arm/hand 的有效动作帧占比（OR 融合）。使用 P20 动态阈值 + 绝对最小值门控，避免微小噪声被计为有效训练信号。',
            weight=self.p.get('lq01_weight', 0.38),
        )

    def _information_density(self) -> MetricResult:
        arm_delta = self.f.action_delta_arm_norm
        hand_delta = self.f.action_delta_hand_norm
        state_arm = self.f.state_delta_arm_norm
        state_hand = self.f.state_delta_hand_norm

        eps_arm = self.p.get('lq02_eps_arm', 0.004)
        eps_hand_val = self.p.get('lq02_eps_hand', 3.0 / 255.0)
        tau_arm = max(float(np.nanpercentile(arm_delta, 20)) if arm_delta.size > 1 else eps_arm, eps_arm)
        tau_hand = max(float(np.nanpercentile(hand_delta, 20)) if hand_delta.size > 1 else eps_hand_val, eps_hand_val)
        effective = (arm_delta > tau_arm) | (hand_delta > tau_hand)
        r_eff = float(np.mean(effective)) if effective.size else 0.0

        action_max = np.maximum(arm_delta, hand_delta)
        i_a = float(np.nanpercentile(action_max[effective], 75)) if effective.any() and action_max[effective].size else 0.0

        state_max = np.maximum(state_arm, state_hand)
        i_q = safe_percentile(state_max, 75, 0.0)

        w_cov = self.p.get('lq02_coverage_weight', 0.7)
        w_state = self.p.get('lq02_state_weight', 0.3)
        raw = w_cov * (r_eff * i_a) + w_state * i_q
        good = self.p.get('lq02_good', 0.030)
        warn = self.p.get('lq02_warn', 0.012)
        bad = self.p.get('lq02_bad', 0.003)
        score = clamp(score_ratio(raw, good=good, warn=warn, bad=bad))
        return MetricResult(
            metricId='LQ-02',
            name='信息密度',
            qualityDimension='learnability',
            evidenceId='EV-LEARN-INFORMATION-DENSITY',
            value=raw,
            valueText=f'{raw:.4f}',
            unit='密度指数',
            score=score,
            level=self._level(score),
            description='覆盖率 × 强度模型：有效覆盖率 × 动作强度 + 状态强度。分离 arm/hand 并用 max 融合，避免静态控制器拉低信息密度估计。',
            weight=self.p.get('lq02_weight', 0.34),
        )

    def _low_value_segment_ratio(self, timeline: list[dict]) -> MetricResult:
        arm_delta = self.f.action_delta_arm_norm
        hand_delta = self.f.action_delta_hand_norm
        state_arm = self.f.state_delta_arm_norm
        state_hand = self.f.state_delta_hand_norm
        duration = self.f.duration

        eps_arm = self.p.get('lq03_eps_arm', 0.004)
        eps_hand_val = self.p.get('lq03_eps_hand', 3.0 / 255.0)
        tau_arm = max(float(np.nanpercentile(arm_delta, 20)) if arm_delta.size > 1 else eps_arm, eps_arm)
        tau_hand = max(float(np.nanpercentile(hand_delta, 20)) if hand_delta.size > 1 else eps_hand_val, eps_hand_val)
        effective = (arm_delta > tau_arm) | (hand_delta > tau_hand)

        state_max = np.maximum(state_arm, state_hand)
        tau_q_floor = self.p.get('lq03_tau_q_floor', 5e-4)
        tau_q = max(tau_q_floor, float(np.nanpercentile(state_max, 20)) if state_max.size > 1 else tau_q_floor)

        low_value = (~effective) & (state_max <= tau_q)

        raw_segs = mask_to_segments(
            low_value, self.f.t_rel,
            label='低价值候选段', level='warn',
            source_metric_id='LQ-03', source_evidence_id='EV-LEARN-LOW-VALUE-SEGMENT',
            quality_dimension='learnability',
            min_dur=0.0, gap_merge=0.3, confidence=0.75,
        )
        min_seg = self.p.get('lq03_min_seg_dur', 1.0)
        t_low = sum(max(s['endSec'] - s['startSec'], 0.0) for s in raw_segs if (s['endSec'] - s['startSec']) >= min_seg)
        ratio = t_low / duration if duration > 0 else 0.0
        good = self.p.get('lq03_good', 0.18)
        warn = self.p.get('lq03_warn', 0.38)
        bad = self.p.get('lq03_bad', 0.65)
        score = clamp(score_inverse(ratio, good=good, warn=warn, bad=bad))

        timeline.extend(mask_to_segments(
            low_value, self.f.t_rel,
            label='低学习价值片段',
            level='warn' if score >= 5 else 'bad',
            source_metric_id='LQ-03',
            source_evidence_id='EV-LEARN-LOW-VALUE-SEGMENT',
            quality_dimension='learnability',
            min_dur=min_seg, gap_merge=0.3,
            confidence=0.75,
        ))
        return MetricResult(
            metricId='LQ-03',
            name='低价值片段比',
            qualityDimension='learnability',
            evidenceId='EV-LEARN-LOW-VALUE-SEGMENT',
            value=ratio,
            valueText=f'{ratio * 100:.1f}%',
            unit='比例',
            score=score,
            level=self._level(score),
            description='长持续时间低学习价值片段占比。复用 LQ-01 有效动作判定，仅惩罚持续性无监督信号区间，不惩罚短暂停顿。',
            weight=self.p.get('lq03_weight', 0.28),
        )

    def _timestamp_regularity(self, timeline: list[dict]) -> MetricResult:
        w_di01 = self.p.get('di01_weight', 0.45)
        depth_dt = self.f.depth_dt

        if depth_dt is not None and depth_dt.size > 0:
            return self._timestamp_regularity_depth(depth_dt, w_di01)

        dt = self.f.dt
        n_dt = dt.size
        if n_dt == 0:
            return MetricResult(
                metricId='DI-01', name='时间戳规则性', qualityDimension='data_integrity',
                evidenceId='EV-DATA-TIMESTAMP', value=1.0, valueText='1.0000', unit='指数',
                score=0.0, level='bad',
                description='无有效时间戳数据。', weight=w_di01,
            )

        valid_dt = dt[dt > 0]
        r_invalid = 1.0 - valid_dt.size / max(n_dt, 1)
        dt_med = float(np.median(valid_dt)) if valid_dt.size else 1.0

        declared_fps = self.f.declared_fps
        use_declared = declared_fps > 0
        expected_interval = 1.0 / declared_fps if use_declared else dt_med

        # Jitter: deviation from expected interval (declared FPS or dt_median fallback)
        jitter = np.abs(dt - expected_interval) / (expected_interval + 1e-6)
        j_95 = float(np.nanpercentile(jitter, 95)) if jitter.size else 0.0

        # Drop frame: gap > drop_mult × expected_interval
        drop_mult = self.p.get('di01_drop_multiplier', 1.5)
        r_gap = float(np.mean(dt > drop_mult * expected_interval)) if dt.size else 0.0

        w_j = self.p.get('di01_jitter_weight', 0.35)
        w_g = self.p.get('di01_gap_weight', 0.25)
        w_i = self.p.get('di01_invalid_weight', 0.15)
        w_fps = self.p.get('di01_fps_weight', 0.25)
        raw = w_j * j_95 + w_g * r_gap + w_i * r_invalid

        description_parts = [f'J_95={j_95:.4f}', f'R_gap={r_gap:.4f}', f'R_invalid={r_invalid:.4f}']

        # FPS consistency: only meaningful when declared FPS is available
        if use_declared:
            fps_error = abs(dt_med - expected_interval) / (expected_interval + 1e-6)
            raw += w_fps * fps_error
            description_parts.append(f'FPS_err={fps_error:.4f}')
            if fps_error > 0.1:
                timeline.append({
                    'start': 0.0, 'end': round(float(self.f.duration), 3),
                    'startSec': 0.0, 'endSec': round(float(self.f.duration), 3),
                    'level': 'warn',
                    'label': f'FPS一致性偏差 (声明{declared_fps:.0f}fps, 实际{1.0/dt_med:.1f}fps)',
                    'sourceMetricId': 'DI-01', 'sourceEvidenceId': 'EV-DATA-TIMESTAMP',
                    'qualityDimension': 'data_integrity',
                    'rawValue': round(float(fps_error), 4), 'threshold': 0.1,
                    'confidence': 0.85,
                })

        good = self.p.get('di01_good', 0.05)
        warn = self.p.get('di01_warn', 0.15)
        bad = self.p.get('di01_bad', 0.35)
        score = clamp(score_inverse(raw, good=good, warn=warn, bad=bad))

        mask_invalid = dt <= 0
        mask_gap = dt > drop_mult * expected_interval
        timeline.extend(mask_to_segments(
            mask_invalid, self.f.t_rel,
            label='非单调时间戳',
            level='bad', source_metric_id='DI-01', source_evidence_id='EV-DATA-TIMESTAMP',
            quality_dimension='data_integrity', min_dur=0.0, gap_merge=0.1, confidence=0.9,
        ))
        timeline.extend(mask_to_segments(
            mask_gap, self.f.t_rel,
            label='疑似丢帧',
            level='warn', source_metric_id='DI-01', source_evidence_id='EV-DATA-TIMESTAMP',
            quality_dimension='data_integrity', min_dur=0.0, gap_merge=0.3, confidence=0.85,
        ))

        desc = '时间戳规则性：' + ' + '.join(description_parts)
        if use_declared:
            desc += f'。基于声明FPS={declared_fps:.0f}计算期望间隔'
        else:
            desc += '。基于dt中位数计算（无声明FPS）'

        return MetricResult(
            metricId='DI-01', name='时间戳规则性', qualityDimension='data_integrity',
            evidenceId='EV-DATA-TIMESTAMP', value=raw, valueText=f'{raw:.4f}', unit='指数',
            score=score, level=self._level(score),
            description=desc,
            weight=w_di01,
        )

    def _timestamp_regularity_depth(self, depth_dt: np.ndarray, w_di01: float) -> MetricResult:
        n_dt = depth_dt.size
        if n_dt == 0:
            return MetricResult(
                metricId='DI-01', name='时间戳规则性', qualityDimension='data_integrity',
                evidenceId='EV-DATA-TIMESTAMP', value=1.0, valueText='1.0000', unit='指数',
                score=0.0, level='bad',
                description='深度相机无有效时间戳数据。', weight=w_di01,
            )

        valid_dt = depth_dt[depth_dt > 0]
        r_invalid = 1.0 - valid_dt.size / max(n_dt, 1)
        dt_med = float(np.median(valid_dt)) if valid_dt.size else 1.0
        expected_interval = dt_med

        # Jitter: deviation from expected interval
        jitter = np.abs(depth_dt - expected_interval) / (expected_interval + 1e-6)
        j_95 = float(np.nanpercentile(jitter, 95)) if jitter.size else 0.0

        # Drop frame: gap > drop_mult × expected_interval
        drop_mult = self.p.get('di01_drop_multiplier', 1.5)
        r_gap = float(np.mean(depth_dt > drop_mult * expected_interval)) if depth_dt.size else 0.0

        w_j = self.p.get('di01_jitter_weight', 0.35)
        w_g = self.p.get('di01_gap_weight', 0.25)
        w_i = self.p.get('di01_invalid_weight', 0.15)
        raw = w_j * j_95 + w_g * r_gap + w_i * r_invalid

        good = self.p.get('di01_good', 0.05)
        warn = self.p.get('di01_warn', 0.15)
        bad = self.p.get('di01_bad', 0.35)
        score = clamp(score_inverse(raw, good=good, warn=warn, bad=bad))

        return MetricResult(
            metricId='DI-01', name='时间戳规则性', qualityDimension='data_integrity',
            evidenceId='EV-DATA-TIMESTAMP', value=raw, valueText=f'{raw:.4f}', unit='指数',
            score=score, level=self._level(score),
            description=f'深度相机时间戳规则性（非合成轴，基准={1.0/dt_med:.1f}fps）：J_95={j_95:.4f} + R_gap={r_gap:.4f} + R_invalid={r_invalid:.4f}。仅评分，不输出时间轴警告。',
            weight=w_di01,
        )

    def _sync_validity(self, timeline: list[dict]) -> MetricResult:
        valid = self.f.sync_valid
        diff = self.f.sync_diff_sec
        dt = self.f.dt
        n = valid.size
        w_di02 = self.p.get('di02_weight', 0.55)

        if n == 0:
            return MetricResult(
                metricId='DI-02', name='传感器同步有效性', qualityDimension='data_integrity',
                evidenceId='EV-DATA-SYNC', value=1.0, valueText='100.0%', unit='指数',
                score=0.0, level='bad',
                description='无有效同步数据。', weight=w_di02,
            )

        valid_dt = dt[dt > 0]
        dt_med = float(np.median(valid_dt)) if valid_dt.size else 0.05
        tw_mult = self.p.get('di02_tau_warn_mult', 2.0)
        tw_floor = self.p.get('di02_tau_warn_floor', 0.05)
        tb_mult = self.p.get('di02_tau_bad_mult', 6.0)
        tb_floor = self.p.get('di02_tau_bad_floor', 0.20)
        tau_warn = max(tw_floor, tw_mult * dt_med)
        tau_bad = max(tb_floor, tb_mult * dt_med)

        r_flag = float(np.mean(~valid)) if n else 0.0
        r_soft = float(np.mean(diff > tau_warn))
        r_hard = float(np.mean(diff > tau_bad))
        m_sync = min(float(np.nanpercentile(diff, 95)) / max(tau_bad, 1e-6), 1.0) if diff.size else 0.0

        anomaly = (~valid) | (diff > tau_warn)
        raw_segs = mask_to_segments(
            anomaly, self.f.t_rel,
            label='同步异常候选段', level='warn',
            source_metric_id='DI-02', source_evidence_id='EV-DATA-SYNC',
            quality_dimension='data_integrity', min_dur=0.0, gap_merge=0.3, confidence=0.9,
        )
        t_total = self.f.duration
        t_seg = sum(max(s['endSec'] - s['startSec'], 0.0) for s in raw_segs if (s['endSec'] - s['startSec']) >= 0.5)
        r_seg = t_seg / t_total if t_total > 0 else 0.0

        w_f = self.p.get('di02_w_flag', 0.30)
        w_h = self.p.get('di02_w_hard', 0.25)
        w_s = self.p.get('di02_w_soft', 0.20)
        w_m = self.p.get('di02_w_sync', 0.15)
        w_seg = self.p.get('di02_w_seg', 0.10)
        raw = w_f * r_flag + w_h * r_hard + w_s * r_soft + w_m * m_sync + w_seg * r_seg
        good = self.p.get('di02_good', 0.06)
        warn = self.p.get('di02_warn', 0.15)
        bad = self.p.get('di02_bad', 0.35)
        score = clamp(score_inverse(raw, good=good, warn=warn, bad=bad))

        timeline.extend(mask_to_segments(
            diff > tau_warn, self.f.t_rel,
            label='同步偏差',
            level='warn', source_metric_id='DI-02', source_evidence_id='EV-DATA-SYNC',
            quality_dimension='data_integrity', min_dur=0.5, gap_merge=0.3,
            raw_values=diff, threshold=tau_warn, confidence=0.9,
        ))
        severe = (~valid) | (diff > tau_bad)
        timeline.extend(mask_to_segments(
            severe, self.f.t_rel,
            label='严重同步错位',
            level='bad', source_metric_id='DI-02', source_evidence_id='EV-DATA-SYNC',
            quality_dimension='data_integrity', min_dur=0.5, gap_merge=0.3,
            raw_values=diff, threshold=tau_bad, confidence=0.9,
        ))
        return MetricResult(
            metricId='DI-02', name='传感器同步有效性', qualityDimension='data_integrity',
            evidenceId='EV-DATA-SYNC', value=raw, valueText=f'{raw * 100:.1f}%', unit='指数',
            score=score, level=self._level(score),
            description='自适应同步有效性：R_flag+R_hard+R_soft+M_sync+R_seg。使用 dt_median 自适应阈值替代固定 700ms，区分轻微偏差与严重错位。',
            weight=w_di02,
        )

    def _command_tracking_error(self, timeline: list[dict]) -> MetricResult:
        err = self.f.tracking_error_weighted
        if err.size == 0:
            return MetricResult(
                metricId='DX-01', name='执行跟踪诊断', qualityDimension='execution_diagnostics',
                evidenceId='EV-DIAG-EXECUTION-TRACKING', value=1.0, valueText='1.000', unit='严重度',
                score=0.0, level='bad', description='无有效跟踪数据。', confidence=0.8, weight=0.0,
            )
        N = err.size
        max_lag = min(self.p.get('dx01_max_lag', 5), N // self.p.get('dx01_lag_ratio', 10))
        best_k, best_median = 0, float(np.nanmedian(err)) if err.size else 0.0
        for k in range(1, max_lag + 1):
            med = float(np.nanmedian(err[k:])) if err[k:].size else float('inf')
            if med < best_median:
                best_median, best_k = med, k
        err_aligned = err[best_k:] if best_k > 0 and err.size > best_k else err

        e_mean = safe_mean(err_aligned, 0.0)
        e_p95 = safe_percentile(err_aligned, 95, 0.0)
        tau_warn = self.p.get('dx01_tau_warn', 0.20)
        tau_bad = self.p.get('dx01_tau_bad', 0.35)
        r_persist = float(np.mean(err_aligned > tau_warn)) if err_aligned.size else 0.0

        severity = clamp(
            self.p.get('dx01_w_p95', 0.5) * min(e_p95 / max(tau_bad, 1e-6), 1.0) +
            self.p.get('dx01_w_mean', 0.3) * min(e_mean / max(tau_warn, 1e-6), 1.0) +
            self.p.get('dx01_w_persist', 0.2) * r_persist
        )
        score = clamp(10.0 * (1.0 - severity))
        level = 'bad' if score < 3.0 else ('warn' if score < 5.0 else 'good')

        timeline.extend(mask_to_segments(
            err_aligned > tau_warn, self.f.t_rel[best_k:] if best_k > 0 else self.f.t_rel,
            label='执行跟踪偏差',
            level='warn', source_metric_id='DX-01', source_evidence_id='EV-DIAG-EXECUTION-TRACKING',
            quality_dimension='execution_diagnostics', min_dur=0.5, gap_merge=0.3,
            raw_values=err_aligned, threshold=tau_warn, confidence=0.8,
        ))
        timeline.extend(mask_to_segments(
            err_aligned > tau_bad, self.f.t_rel[best_k:] if best_k > 0 else self.f.t_rel,
            label='严重跟踪偏差',
            level='bad', source_metric_id='DX-01', source_evidence_id='EV-DIAG-EXECUTION-TRACKING',
            quality_dimension='execution_diagnostics', min_dur=0.5, gap_merge=0.3,
            raw_values=err_aligned, threshold=tau_bad, confidence=0.8,
        ))
        return MetricResult(
            metricId='DX-01', name='执行跟踪诊断', qualityDimension='execution_diagnostics',
            evidenceId='EV-DIAG-EXECUTION-TRACKING', value=severity, valueText=f'{severity:.3f}', unit='严重度',
            score=score, level=level,
            description=f'执行链路跟踪诊断（lag={best_k}frames）。加权 RMS 误差，使用 lag alignment 对齐。不参与训练质量总分。',
            confidence=0.8, weight=0.0,
        )

    def _data_validity(self) -> MetricResult:
        total = (self.f.actions_nan + self.f.actions_inf
                 + self.f.qpos_nan + self.f.qpos_inf
                 + self.f.effort_nan + self.f.effort_inf
                 + self.f.qvel_nan + self.f.qvel_inf)
        if total == 0:
            return MetricResult(
                metricId='DX-02', name='数据有效性', qualityDimension='data_integrity',
                evidenceId='EV-DATA-VALIDITY', value=0.0, valueText='0', unit='个',
                score=10.0, level='good',
                description='Actions / Qpos / Effort / Qvel 数组未检测到 NaN 或 Inf，数据完整。',
                confidence=0.95, weight=0.0,
            )
        parts = []
        if self.f.actions_nan: parts.append(f'actions NaN={self.f.actions_nan}')
        if self.f.actions_inf: parts.append(f'actions Inf={self.f.actions_inf}')
        if self.f.qpos_nan: parts.append(f'qpos NaN={self.f.qpos_nan}')
        if self.f.qpos_inf: parts.append(f'qpos Inf={self.f.qpos_inf}')
        if self.f.effort_nan: parts.append(f'effort NaN={self.f.effort_nan}')
        if self.f.effort_inf: parts.append(f'effort Inf={self.f.effort_inf}')
        if self.f.qvel_nan: parts.append(f'qvel NaN={self.f.qvel_nan}')
        if self.f.qvel_inf: parts.append(f'qvel Inf={self.f.qvel_inf}')
        severity = min(1.0, total / 100)
        score = clamp(10.0 * (1.0 - severity))
        return MetricResult(
            metricId='DX-02', name='数据有效性', qualityDimension='data_integrity',
            evidenceId='EV-DATA-VALIDITY', value=float(total), valueText=str(total), unit='个',
            score=score, level='bad',
            description='数据发现 NaN/Inf 异常值：' + '；'.join(parts) + '。遥操作数据可能已损坏。',
            confidence=0.95, weight=0.0,
        )

    def _dimension_health(self) -> MetricResult:
        records = self.f.dim_health_records
        if not records:
            return MetricResult(
                metricId='DI-03', name='维度健康', qualityDimension='data_integrity',
                evidenceId='EV-DATA-DIM-HEALTH', value=0.0, valueText='0', unit='个',
                score=10.0, level='good',
                description='无有效维度数据，跳过维度健康检查。',
                confidence=0.8, weight=0.0,
            )

        zero_var_dims = [r for r in records if r['is_zero_variance']]
        outlier_z_threshold = self.p.get('di03_outlier_z', 10)
        outlier_ratio_warn = self.p.get('di03_outlier_ratio_warn', 0.01)
        outlier_dims = [r for r in records if r['outlier_ratio'] > outlier_ratio_warn]

        total_issues = len(zero_var_dims) + len(outlier_dims)
        if total_issues == 0:
            return MetricResult(
                metricId='DI-03', name='维度健康', qualityDimension='data_integrity',
                evidenceId='EV-DATA-DIM-HEALTH', value=0.0, valueText='0', unit='个',
                score=10.0, level='good',
                description=f'全部 {len(records)} 个维度健康：无零方差，无极端异常值。',
                confidence=0.9, weight=0.0,
            )

        desc_parts = []
        for r in zero_var_dims:
            desc_parts.append(f"{r['label']}: 零方差（全段={r['std']:.4f}）")
        for r in outlier_dims:
            desc_parts.append(f"{r['label']}: {r['outlier_ratio']:.1%} 帧为极端异常值（robust_z>{outlier_z_threshold}）")

        severity = min(1.0, total_issues / max(len(records), 1))
        score = clamp(10.0 * (1.0 - severity * 1.5))
        level = 'bad' if zero_var_dims else 'warn'

        return MetricResult(
            metricId='DI-03', name='维度健康', qualityDimension='data_integrity',
            evidenceId='EV-DATA-DIM-HEALTH', value=float(total_issues), valueText=str(total_issues), unit='个',
            score=score, level=level,
            description='；'.join(desc_parts[:6]) + ('...' if len(desc_parts) > 6 else ''),
            confidence=0.9, weight=0.0,
        )

    def _episode_completeness(self) -> MetricResult:
        actual = self.f.t_rel.shape[0] if self.f.t_rel.size else 0
        declared = self.f.manifest_frame_count
        min_frames = self.p.get('di04_min_frames', 10)
        mismatch_ratio = self.p.get('di04_mismatch_ratio', 0.05)

        if actual < min_frames:
            return MetricResult(
                metricId='DI-04', name='Episode 完整性', qualityDimension='data_integrity',
                evidenceId='EV-DATA-EPISODE-COMPLETENESS', value=float(actual), valueText=str(actual), unit='帧',
                score=2.0, level='bad',
                description=f'帧数过短（实际={actual} < 最低={min_frames}），无法可靠计算指标。',
                confidence=0.95, weight=0.0,
            )

        if declared > 0:
            ratio = abs(declared - actual) / declared
            if ratio > mismatch_ratio:
                return MetricResult(
                    metricId='DI-04', name='Episode 完整性', qualityDimension='data_integrity',
                    evidenceId='EV-DATA-EPISODE-COMPLETENESS', value=float(actual), valueText=str(actual), unit='帧',
                    score=7.0, level='warn',
                    description=f'manifest 声明 {declared} 帧，实际 {actual} 帧（偏差 {ratio:.1%}），可能数据截断。',
                    confidence=0.9, weight=0.0,
                )

        return MetricResult(
            metricId='DI-04', name='Episode 完整性', qualityDimension='data_integrity',
            evidenceId='EV-DATA-EPISODE-COMPLETENESS', value=float(actual), valueText=str(actual), unit='帧',
            score=10.0, level='good',
            description=f'帧数充足（实际={actual}，声明={declared if declared else "无"}），episode 结构完整。',
            confidence=0.95, weight=0.0,
        )
