from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .telemetry_parser import ParsedTelemetry
from .utils import safe_mean


@dataclass
class L3V2Features:
    t_rel: np.ndarray
    dt: np.ndarray
    fps: float
    duration: float
    joint_action_delta_norm: np.ndarray
    joint_state_delta_norm: np.ndarray
    joint_jerk_norm: np.ndarray
    action_discontinuity_strength: np.ndarray
    reversal_rate_per_frame: np.ndarray
    hand_chatter_strength: np.ndarray
    tracking_error_weighted: np.ndarray
    low_change_mask: np.ndarray
    sync_bad_mask: np.ndarray
    timestamp_jitter_cv: float


class FeatureExtractor:
    """Feature layer: derive reusable numeric features from parsed telemetry."""

    def __init__(self, telemetry: ParsedTelemetry):
        self.t = telemetry

    def extract(self) -> L3V2Features:
        t_rel = self.t.t_rel
        n = self.t.n
        dt = np.diff(t_rel)
        valid_dt = dt[dt > 0]
        fps = self.t.fps
        duration = self.t.duration
        jitter_cv = float(np.std(valid_dt) / np.mean(valid_dt)) if valid_dt.size >= 2 and np.mean(valid_dt) > 0 else 0.0

        action_delta = np.diff(self.t.actions, axis=0) if n >= 2 else np.zeros((0, self.t.actions.shape[1]))
        state_delta = np.diff(self.t.qpos, axis=0) if n >= 2 else np.zeros((0, self.t.qpos.shape[1]))
        joint_action_delta_norm = self._row_norm(action_delta, n)
        joint_state_delta_norm = self._row_norm(state_delta, n)

        jerk_arm = np.diff(self.t.qpos_arm, n=2, axis=0) if self.t.qpos_arm.shape[0] >= 3 else np.zeros((0, self.t.qpos_arm.shape[1]))
        joint_jerk_norm = self._row_norm(jerk_arm, n, offset=2)

        # A robust discontinuity signal: action jump relative to the episode's own distribution.
        p95_delta = np.nanpercentile(joint_action_delta_norm[1:], 95) if joint_action_delta_norm.size > 2 else 0.0
        median_delta = np.nanmedian(joint_action_delta_norm[1:]) if joint_action_delta_norm.size > 2 else 0.0
        denom = max(p95_delta - median_delta, 1e-9)
        action_discontinuity_strength = np.clip((joint_action_delta_norm - median_delta) / denom, 0.0, 10.0)

        reversal_rate = self._reversal_rate(n)
        hand_chatter = self._hand_chatter_strength(n)
        tracking = self._tracking_error_weighted(n)

        low_change_threshold = max(np.nanpercentile(joint_action_delta_norm, 25) if n > 4 else 0.0, 1e-4)
        low_state_threshold = max(np.nanpercentile(joint_state_delta_norm, 25) if n > 4 else 0.0, 1e-4)
        low_change_mask = (joint_action_delta_norm <= low_change_threshold) & (joint_state_delta_norm <= low_state_threshold)

        sync_bad_mask = (~self.t.sync_valid) | (self.t.sync_diff_ms > 700.0)

        return L3V2Features(
            t_rel=t_rel,
            dt=dt,
            fps=fps,
            duration=duration,
            joint_action_delta_norm=joint_action_delta_norm,
            joint_state_delta_norm=joint_state_delta_norm,
            joint_jerk_norm=joint_jerk_norm,
            action_discontinuity_strength=action_discontinuity_strength,
            reversal_rate_per_frame=reversal_rate,
            hand_chatter_strength=hand_chatter,
            tracking_error_weighted=tracking,
            low_change_mask=low_change_mask,
            sync_bad_mask=sync_bad_mask,
            timestamp_jitter_cv=jitter_cv,
        )

    @staticmethod
    def _row_norm(values: np.ndarray, target_n: int, offset: int = 1) -> np.ndarray:
        out = np.zeros(target_n, dtype=np.float64)
        if values.size == 0:
            return out
        norm = np.sqrt(np.nanmean(values ** 2, axis=1)) if values.ndim == 2 and values.shape[1] else np.zeros(values.shape[0])
        end = min(target_n, offset + norm.shape[0])
        out[offset:end] = norm[:max(0, end - offset)]
        return out

    def _reversal_rate(self, target_n: int) -> np.ndarray:
        actions = self.t.actions
        out = np.zeros(target_n, dtype=np.float64)
        if actions.shape[0] < 3 or actions.shape[1] == 0:
            return out
        delta = np.diff(actions, axis=0)
        signs = np.sign(delta)
        reversals = (signs[1:] * signs[:-1]) < 0
        out[2:] = np.nanmean(reversals.astype(float), axis=1)
        return out

    def _hand_chatter_strength(self, target_n: int) -> np.ndarray:
        ah = self.t.actions_hand
        out = np.zeros(target_n, dtype=np.float64)
        if ah.shape[0] < 2 or ah.shape[1] == 0:
            return out
        delta = np.abs(np.diff(ah, axis=0))
        out[1:] = np.nanmean(delta > (2.0 / 255.0), axis=1)
        return out

    def _tracking_error_weighted(self, target_n: int) -> np.ndarray:
        out = np.zeros(target_n, dtype=np.float64)
        arm_err = np.zeros(target_n, dtype=np.float64)
        hand_err = np.zeros(target_n, dtype=np.float64)
        if self.t.actions_arm.shape[1] and self.t.qpos_arm.shape[1]:
            arm_err = np.nanmean(np.abs(self.t.actions_arm - self.t.qpos_arm), axis=1)
        if self.t.actions_hand.shape[1] and self.t.qpos_hand.shape[1]:
            hand_err = np.nanmean(np.abs(self.t.actions_hand - self.t.qpos_hand), axis=1)
        if self.t.actions_arm.shape[1] and self.t.actions_hand.shape[1]:
            out = 0.7 * arm_err + 0.3 * hand_err
        elif self.t.actions_arm.shape[1]:
            out = arm_err
        elif self.t.actions_hand.shape[1]:
            out = hand_err
        return out
