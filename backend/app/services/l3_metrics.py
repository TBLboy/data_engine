import numpy as np
from dataclasses import dataclass
from typing import Any


@dataclass
class L3HyperParams:
    arm_joint_count: int = 7
    eps_arm: float = 0.01
    eps_hand: float = 0.02
    dead_good: float = 0.10
    dead_warn: float = 0.25
    sat_margin: float = 0.05
    sat_hand_low: float = 10.0
    sat_hand_high: float = 245.0
    sat_good: float = 0.03
    sat_warn: float = 0.08
    static_window_s: float = 0.5
    static_arm_vel: float = 0.01
    static_arm_act: float = 0.01
    static_hand_act: float = 0.02
    static_good: float = 0.08
    static_warn: float = 0.20
    jitter_good: float = 0.02
    jitter_warn: float = 0.05
    tracking_arm_weight: float = 0.7
    tracking_hand_weight: float = 0.3
    tracking_good: float = 0.12
    tracking_warn: float = 0.20
    ldlj_good: float = 7.0
    ldlj_warn: float = 5.0
    chatter_threshold: float = 2.0
    chatter_good: float = 1.0
    chatter_warn: float = 2.0
    effort_good: float = 0.9
    effort_warn: float = 1.5
    timeline_min_dur: float = 0.5
    timeline_gap_merge: float = 0.3
    sync_bad_threshold_ms: float = 700.0
    ldlj_max_val: float = 0.05  # 用于归一化 jerk 的参考上限

    @property
    def qmotion_weights(self) -> dict:
        return {
            'ldlj': 0.18,
            'dead': 0.15,
            'sat': 0.10,
            'static': 0.15,
            'jitter': 0.07,
            'tracking': 0.20,
            'chatter': 0.05,
            'effort': 0.10,
        }


DEFAULT_PARAMS = L3HyperParams()

def _level(v: float, warn: float, bad: float, reverse: bool = False) -> str:
    if reverse:
        if v <= bad: return "bad"
        if v <= warn: return "warn"
        return "good"
    if v >= bad: return "bad"
    if v >= warn: return "warn"
    return "good"


def _sliding_window_mask(condition_mask: np.ndarray, win: int) -> np.ndarray:
    """Return True for frames where >= win/2 frames in a window of size win satisfy condition."""
    if win <= 1 or len(condition_mask) < win:
        return condition_mask.copy()
    kernel = np.ones(win)
    conv = np.convolve(condition_mask.astype(float), kernel, mode='same')
    return conv >= (win * 0.5)


def _mask_to_segments(mask: np.ndarray, t_rel: np.ndarray, label: str, level: str) -> list:
    if not mask.any():
        return []
    segs = []
    start = None
    for i, a in enumerate(mask.tolist()):
        if a and start is None:
            start = i
        if not a and start is not None:
            segs.append({"start": int(round(float(t_rel[start]))), "end": int(round(float(t_rel[i - 1]))), "level": level, "label": label})
            start = None
    if start is not None:
        segs.append({"start": int(round(float(t_rel[start]))), "end": int(round(float(t_rel[-1]))), "level": level, "label": label})
    return segs


def _merge_segments(segments: list, max_gap: float = 0.3, min_dur: float = 0.5) -> list:
    if not segments:
        return []
    ordered = sorted(segments, key=lambda s: (s["label"], s["start"], s["end"]))
    merged = []
    for s in ordered:
        if not merged:
            merged.append(dict(s))
            continue
        cur = merged[-1]
        if cur["label"] == s["label"] and cur["level"] == s["level"] and s["start"] <= cur["end"] + max_gap:
            cur["end"] = max(cur["end"], s["end"])
        else:
            merged.append(dict(s))
    for s in merged:
        if s["end"] - s["start"] < min_dur:
            s["end"] = s["start"] + int(min_dur)
    return sorted(merged, key=lambda s: (s["start"], s["label"]))


class L3MetricsEngine:
    """Episode-level L3 metric computation."""

    def __init__(self, telemetry: dict, params: L3HyperParams | None = None):
        self.p = params or DEFAULT_PARAMS
        ts = telemetry["timestamps"].astype(np.float64)
        self.t_rel = ts - ts[0]
        self.qpos = telemetry["qpos"].astype(np.float64)
        self.qvel = telemetry["qvel"].astype(np.float64)
        self.actions = telemetry["actions"].astype(np.float64)
        self.effort = telemetry["effort"].astype(np.float64)
        self.sync_valid = telemetry["sync_validation_is_valid"]
        self.sync_diff = telemetry["sync_validation_max_diff"].astype(np.float64)
        self._n = len(self.t_rel)
        self._ac = self.p.arm_joint_count
        self._split()

    def _split(self):
        qpos_range = np.max(self.qpos, axis=0) - np.min(self.qpos, axis=0)
        active_dims = qpos_range > 1e-8
        qpos_active = np.max(np.abs(self.qpos[:, active_dims]), axis=0)
        self._arm_mask_active = qpos_active <= 3.5
        self._hand_mask_active = ~self._arm_mask_active
        active_indices = np.where(active_dims)[0]
        self._arm_dims = list(active_indices[self._arm_mask_active])
        self._hand_dims = list(active_indices[self._hand_mask_active])

        self.qpos_arm = self.qpos[:, self._arm_dims] if self._arm_dims else np.zeros((self._n, 0))
        self.qpos_hand = self.qpos[:, self._hand_dims] / 255.0 if self._hand_dims else np.zeros((self._n, 0))
        self.qvel_arm = self.qvel[:, self._arm_dims] if self._arm_dims else np.zeros((self._n, 0))
        self.qvel_hand = self.qvel[:, self._hand_dims] if self._hand_dims else np.zeros((self._n, 0))
        self.actions_arm = self.actions[:, self._arm_dims] if self._arm_dims else np.zeros((self._n, 0))
        self.actions_hand_raw = self.actions[:, self._hand_dims] if self._hand_dims else np.zeros((self._n, 0))
        self.actions_hand = self.actions_hand_raw / 255.0
        self.effort_arm = self.effort[:, self._arm_dims] if self._arm_dims else np.zeros((self._n, 0))

    # ----------------------------------------------------------------
    # P0-1: LDLJ Smoothness
    # ----------------------------------------------------------------

    def _compute_ldlj(self) -> dict:
        qa = self.qpos_arm
        if len(qa) < 3:
            return {"key": "ldlj", "label": "平滑度 LDLJ*", "value": "--", "level": "good", "description": "平滑度指标需要至少3帧数据才能计算"}
        jerk = np.abs(np.diff(qa, n=2, axis=0)).mean(axis=1)
        jerk_rms = float(np.sqrt(np.mean(jerk ** 2)))
        score = max(0.0, min(10.0, 10.0 * (1.0 - min(jerk_rms / self.p.ldlj_max_val, 1.0))))
        return {
            "key": "ldlj",
            "label": "平滑度 LDLJ*",
            "value": f"{score:.1f}",
            "level": _level(score, self.p.ldlj_good, self.p.ldlj_warn, reverse=True),
            "description": "LDLJ dimensionless jerk 平滑度。分数越高动作越顺滑自然"
        }

    # ----------------------------------------------------------------
    # P0-2: Dead Actions
    # ----------------------------------------------------------------

    def _compute_dead(self) -> dict:
        arm_dead_mask = np.all(np.abs(self.actions_arm) < self.p.eps_arm, axis=1)
        hand_dead_mask = np.all(np.abs(self.actions_hand) < self.p.eps_hand, axis=1)
        arm_dead = float(np.mean(arm_dead_mask))
        hand_dead = float(np.mean(hand_dead_mask))
        val = max(arm_dead, hand_dead)
        return {
            "key": "dead",
            "label": "无效动作占比",
            "value": f"{val * 100:.1f}%",
            "level": _level(val, self.p.dead_good, self.p.dead_warn),
            "description": f"arm:{arm_dead*100:.1f}% hand:{hand_dead*100:.1f}% 帧动作幅值低于检测下限的比例"
        }

    def _dead_timeline(self) -> list:
        mask = np.all(np.abs(self.actions_arm) < self.p.eps_arm, axis=1) | np.all(np.abs(self.actions_hand) < self.p.eps_hand, axis=1)
        return _mask_to_segments(mask, self.t_rel, "动作消失", "warn")

    # ----------------------------------------------------------------
    # P0-3: Action Saturation
    # ----------------------------------------------------------------

    def _compute_saturation(self) -> dict:
        aa = self.actions_arm
        arm_sat = 0.0
        if aa.shape[1] > 0:
            lo = np.percentile(aa, 1, axis=0) - self.p.sat_margin
            hi = np.percentile(aa, 99, axis=0) + self.p.sat_margin
            arm_sat_mask = np.any(aa <= lo, axis=1) | np.any(aa >= hi, axis=1)
            arm_sat = float(np.mean(arm_sat_mask))
        ah = self.actions_hand_raw
        hand_sat = 0.0
        if ah.shape[1] > 0:
            hand_sat_mask = np.any(ah <= self.p.sat_hand_low, axis=1) | np.any(ah >= self.p.sat_hand_high, axis=1)
            hand_sat = float(np.mean(hand_sat_mask))
        val = max(arm_sat, hand_sat)
        return {
            "key": "saturation",
            "label": "动作饱和率",
            "value": f"{val * 100:.1f}%",
            "level": _level(val, self.p.sat_good, self.p.sat_warn),
            "description": f"arm:{arm_sat*100:.1f}% hand:{hand_sat*100:.1f}% 动作值接近关节物理边界或0/255的比例"
        }

    def _saturation_timeline(self) -> list:
        combined = np.zeros(self._n, dtype=bool)
        aa = self.actions_arm
        if aa.shape[1] > 0:
            lo = np.percentile(aa, 1, axis=0) - self.p.sat_margin
            hi = np.percentile(aa, 99, axis=0) + self.p.sat_margin
            combined |= np.any(aa <= lo, axis=1) | np.any(aa >= hi, axis=1)
        ah = self.actions_hand_raw
        if ah.shape[1] > 0:
            combined |= np.any(ah <= self.p.sat_hand_low, axis=1) | np.any(ah >= self.p.sat_hand_high, axis=1)
        return _mask_to_segments(combined, self.t_rel, "动作饱和", "warn")

    # ----------------------------------------------------------------
    # P0-4: Static Detection
    # ----------------------------------------------------------------

    def _compute_static(self) -> dict:
        ws = max(1, int(self.p.static_window_s * (self._n / max(float(self.t_rel[-1]), 1e-6))))
        if self._n < 2:
            return {"key": "static", "label": "停滞占比", "value": "0.0%", "level": "good", "description": "帧数不足无法计算停滞占比"}
        arm_mag = np.abs(self.actions_arm).mean(axis=1)
        arm_vel_mag = np.abs(self.qvel_arm).mean(axis=1)
        hand_mag = np.abs(self.actions_hand).mean(axis=1)
        arm_slow = (arm_mag < self.p.static_arm_act) & (arm_vel_mag < self.p.static_arm_vel)
        hand_slow = hand_mag < self.p.static_hand_act
        arm_mask = _sliding_window_mask(arm_slow, ws)
        hand_mask = _sliding_window_mask(hand_slow, ws) if hand_slow.shape[0] > 0 else np.zeros(self._n, dtype=bool)
        mask = arm_mask | hand_mask
        val = float(np.mean(mask))
        return {
            "key": "static",
            "label": "停滞占比",
            "value": f"{val * 100:.1f}%",
            "level": _level(val, self.p.static_good, self.p.static_warn),
            "description": f"arm/hand 速度与动作持续低于检测下限 {self.p.static_window_s}s 窗口帧占比"
        }

    def _static_timeline(self) -> list:
        ws = max(1, int(self.p.static_window_s * (self._n / max(float(self.t_rel[-1]), 1e-6))))
        if self._n < 2:
            return []
        arm_mag = np.abs(self.actions_arm).mean(axis=1)
        arm_vel_mag = np.abs(self.qvel_arm).mean(axis=1)
        hand_mag = np.abs(self.actions_hand).mean(axis=1)
        arm_slow = (arm_mag < self.p.static_arm_act) & (arm_vel_mag < self.p.static_arm_vel)
        hand_slow = hand_mag < self.p.static_hand_act
        arm_mask = _sliding_window_mask(arm_slow, ws)
        hand_mask = _sliding_window_mask(hand_slow, ws) if hand_slow.shape[0] > 0 else np.zeros(self._n, dtype=bool)
        return _mask_to_segments(arm_mask | hand_mask, self.t_rel, "运动停滞", "warn")

    # ----------------------------------------------------------------
    # P0-5: Timestamp Jitter
    # ----------------------------------------------------------------

    def _compute_jitter(self) -> dict:
        if self._n < 2:
            return {"key": "jitter", "label": "时间戳抖动", "value": "--", "level": "good", "description": "帧数不足无法计算抖动"}
        dt = np.diff(self.t_rel)
        dt = dt[dt > 0]
        if len(dt) < 2:
            return {"key": "jitter", "label": "时间戳抖动", "value": "--", "level": "good", "description": "无法计算：有效时间差不足"}
        jitter = float(np.std(dt) / np.mean(dt))
        return {
            "key": "jitter",
            "label": "时间戳抖动",
            "value": f"{jitter:.4f}",
            "level": _level(jitter, self.p.jitter_good, self.p.jitter_warn),
            "description": "采样时间间隔的变异系数 CV=std/mean，过高说明时间戳分布不均匀"
        }

    # ----------------------------------------------------------------
    # P0-6: Qpos-Action Tracking Error
    # ----------------------------------------------------------------

    def _compute_tracking(self) -> dict:
        err_arm = np.abs(self.actions_arm - self.qpos_arm).mean(axis=1)
        err_hand = np.abs(self.actions_hand - self.qpos_hand).mean(axis=1)
        p95_arm = float(np.percentile(err_arm, 95))
        p95_hand = float(np.percentile(err_hand, 95))
        val = self.p.tracking_arm_weight * p95_arm + self.p.tracking_hand_weight * p95_hand
        return {
            "key": "tracking",
            "label": "跟踪误差",
            "value": f"{val:.3f}",
            "level": _level(val, self.p.tracking_good, self.p.tracking_warn),
            "description": f"实际位置与目标命令的加权 P95 误差 (arm:{p95_arm:.3f}×{self.p.tracking_arm_weight} + hand:{p95_hand:.3f}×{self.p.tracking_hand_weight})"
        }

    def _tracking_timeline(self) -> list:
        err_arm = np.abs(self.actions_arm - self.qpos_arm).mean(axis=1)
        err_hand = np.abs(self.actions_hand - self.qpos_hand).mean(axis=1)
        val = self.p.tracking_arm_weight * err_arm + self.p.tracking_hand_weight * err_hand
        mask = val > self.p.tracking_warn
        return _mask_to_segments(mask, self.t_rel, "跟踪误差", "warn")

    # ----------------------------------------------------------------
    # P1-7: Per-finger Gripper Chatter
    # ----------------------------------------------------------------

    def _compute_chatter(self) -> dict:
        ah = self.actions_hand
        if ah.shape[1] == 0:
            return {"key": "chatter", "label": "手指颤振", "value": "--", "level": "good", "description": "当前数据无手部维度"}
        if ah.shape[0] < 2:
            return {"key": "chatter", "label": "手指颤振", "value": "0.0/s", "level": "good", "description": "帧数不足"}
        finger_transitions = np.sum(np.abs(np.diff(ah, axis=0)) > self.p.chatter_threshold / 255.0, axis=1)
        fps = self._n / max(float(self.t_rel[-1]), 1e-6)
        chatter_rate = float(np.mean(finger_transitions)) * fps
        return {
            "key": "chatter",
            "label": "手指颤振",
            "value": f"{chatter_rate:.1f}/s",
            "level": _level(chatter_rate, self.p.chatter_good, self.p.chatter_warn),
            "description": f"手部关节方向切换频率，>{self.p.chatter_threshold} 次方向翻转/秒视为颤振"
        }

    def _chatter_timeline(self) -> list:
        ah = self.actions_hand
        if ah.shape[1] == 0 or ah.shape[0] < 2:
            return []
        ft = np.sum(np.abs(np.diff(ah, axis=0)) > self.p.chatter_threshold / 255.0, axis=1)
        fps = self._n / max(float(self.t_rel[-1]), 1e-6)
        chatter_rate = ft * fps
        mask = np.zeros(self._n, dtype=bool)
        mask[1:] = chatter_rate > self.p.chatter_warn
        return _mask_to_segments(mask, self.t_rel, "手指颤振", "warn")

    # ----------------------------------------------------------------
    # P1-8: Joint Effort
    # ----------------------------------------------------------------

    def _compute_effort(self) -> dict:
        if self.effort_arm.shape[1] == 0:
            return {"key": "effort", "label": "执行力度", "value": "--", "level": "good", "description": "当前数据无 effort 维度"}
        p95 = float(np.percentile(np.abs(self.effort_arm).mean(axis=1), 95))
        return {
            "key": "effort",
            "label": "执行力度",
            "value": f"{p95:.3f}",
            "level": _level(p95, self.p.effort_good, self.p.effort_warn),
            "description": "机械臂关节 effort 的 P95 值，衡量执行过程的吃力程度"
        }

    # ----------------------------------------------------------------
    # Q_motion composite
    # ----------------------------------------------------------------

    def _compute_qmotion(self, cards: list) -> dict:
        w = self.p.qmotion_weights
        scores = []
        for c in cards:
            k = c["key"]
            if k not in w:
                continue
            lv = c["level"]
            if lv == "good":
                scores.append(w[k])
            elif lv == "warn":
                scores.append(w[k] * 0.5)
            elif lv == "bad":
                scores.append(0.0)
        total_w = sum(w.get(c["key"], 0) for c in cards if c["key"] in w)
        if total_w == 0:
            return {"key": "q_motion", "label": "Q_motion", "value": "--", "level": "good", "description": "综合运动质量评分，基于各项子指标的加权合成"}
        raw = sum(scores) / max(total_w, 1e-9)
        score = max(0.0, min(10.0, raw * 10.0))
        return {
            "key": "q_motion",
            "label": "Q_motion",
            "value": f"{score:.1f}",
            "level": _level(score, 6.5, 4.5, reverse=True),
            "description": "综合运动质量评分 0-10。由 8 项指标加权合成：平滑度/无效动作/饱和/停滞/抖动/跟踪误差/颤振/执行力度"
        }

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def compute_all(self) -> dict:
        pc = []
        pc.append(self._compute_ldlj())
        pc.append(self._compute_dead())
        pc.append(self._compute_saturation())
        pc.append(self._compute_static())
        pc.append(self._compute_jitter())
        pc.append(self._compute_tracking())
        pc.append(self._compute_chatter())
        pc.append(self._compute_effort())
        pc.append(self._compute_qmotion(pc))

        tl = []
        tl.extend(self._dead_timeline())
        tl.extend(self._saturation_timeline())
        tl.extend(self._static_timeline())
        tl.extend(self._tracking_timeline())
        tl.extend(self._chatter_timeline())
        sync_mask = self.sync_diff > self.p.sync_bad_threshold_ms
        tl.extend(_mask_to_segments(sync_mask, self.t_rel, "同步异常", "bad"))
        tl = _merge_segments(tl, self.p.timeline_gap_merge, self.p.timeline_min_dur)

        if not tl:
            end_s = int(round(float(self.t_rel[-1]))) if self._n else 0
            tl.append({"start": 0, "end": end_s, "level": "good", "label": "全段正常"})

        return {"metrics": pc, "timelineSegments": tl}
