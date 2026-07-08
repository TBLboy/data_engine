from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .telemetry_parser import ParsedTelemetry
from .utils import safe_mean


@dataclass
class L3V2Features:
    t_rel: np.ndarray
    dt: np.ndarray
    fps: float
    duration: float
    declared_fps: float
    manifest_frame_count: int
    joint_action_delta_norm: np.ndarray
    joint_state_delta_norm: np.ndarray
    action_delta_arm_norm: np.ndarray
    action_delta_hand_norm: np.ndarray
    state_delta_arm_norm: np.ndarray
    state_delta_hand_norm: np.ndarray
    joint_acc_norm: np.ndarray
    joint_jerk_norm: np.ndarray
    action_delta2_norm: np.ndarray
    oscillation_strength: np.ndarray
    chatter_strength: np.ndarray
    tracking_error_weighted: np.ndarray
    sync_valid: np.ndarray
    sync_diff_sec: np.ndarray
    dt_jitter_cv: float
    depth_dt: np.ndarray | None = None
    actions_nan: int = 0
    actions_inf: int = 0
    qpos_nan: int = 0
    qpos_inf: int = 0
    effort_nan: int = 0
    effort_inf: int = 0
    qvel_nan: int = 0
    qvel_inf: int = 0
    dim_health_records: list[dict] = field(default_factory=list)


class FeatureExtractor:
    """Feature layer: derive reusable numeric features from parsed telemetry."""

    def __init__(self, telemetry: ParsedTelemetry, params: dict[str, Any] | None = None, *, depth_timestamps: np.ndarray | None = None, declared_fps: float = 0.0, manifest_frame_count: int = 0):
        self.t = telemetry
        self.p = params or {}
        self.depth_timestamps = depth_timestamps
        self.declared_fps = declared_fps
        self.manifest_frame_count = manifest_frame_count

    def extract(self) -> L3V2Features:
        t_rel = self.t.t_rel
        n = self.t.n
        dt = np.diff(t_rel)
        depth_dt: np.ndarray | None = None
        if self.depth_timestamps is not None and self.depth_timestamps.size >= 2:
            depth_dt = np.diff(self.depth_timestamps)
            if depth_dt.size == 0:
                depth_dt = None
        valid_dt = dt[dt > 0]
        fps = self.t.fps
        duration = self.t.duration
        jitter_cv = float(np.std(valid_dt) / np.mean(valid_dt)) if valid_dt.size >= 2 and np.mean(valid_dt) > 0 else 0.0

        sync_valid_arr = self.t.sync_valid.copy()
        sync_diff_sec_arr = self.t.sync_diff_ms / 1000.0

        action_delta = np.diff(self.t.actions, axis=0) if n >= 2 else np.zeros((0, self.t.actions.shape[1]))
        state_delta = np.diff(self.t.qpos, axis=0) if n >= 2 else np.zeros((0, self.t.qpos.shape[1]))
        joint_action_delta_norm = self._row_norm(action_delta, n)
        joint_state_delta_norm = self._row_norm(state_delta, n)

        action_delta_arm = np.diff(self.t.actions_arm, axis=0) if n >= 2 and self.t.actions_arm.shape[1] else np.zeros((0, 1))
        action_delta_hand = np.diff(self.t.actions_hand, axis=0) if n >= 2 and self.t.actions_hand.shape[1] else np.zeros((0, 1))
        action_delta_arm_norm = self._row_norm(action_delta_arm, n)
        action_delta_hand_norm = self._row_norm(action_delta_hand, n)

        state_delta_arm = np.diff(self.t.qpos_arm, axis=0) if n >= 2 and self.t.qpos_arm.shape[1] else np.zeros((0, 1))
        state_delta_hand = np.diff(self.t.qpos_hand, axis=0) if n >= 2 and self.t.qpos_hand.shape[1] else np.zeros((0, 1))
        state_delta_arm_norm = self._row_norm(state_delta_arm, n)
        state_delta_hand_norm = self._row_norm(state_delta_hand, n)

        acc_arm = np.diff(self.t.qpos_arm, n=2, axis=0) if self.t.qpos_arm.shape[0] >= 3 else np.zeros((0, self.t.qpos_arm.shape[1]))
        jerk_arm = np.diff(self.t.qpos_arm, n=3, axis=0) if self.t.qpos_arm.shape[0] >= 4 else np.zeros((0, self.t.qpos_arm.shape[1]))
        joint_acc_norm = self._row_norm(acc_arm, n, offset=2)
        joint_jerk_norm = self._row_norm(jerk_arm, n, offset=3)

        action_delta2_arm = np.diff(self.t.actions_arm, n=2, axis=0) if n >= 3 and self.t.actions_arm.shape[1] else np.zeros((0, 1))
        action_delta2_norm = self._row_norm(action_delta2_arm, n, offset=2)

        oscillation = self._oscillation_strength_arm(n)
        chatter = self._chatter_strength_hand(n)
        tracking = self._tracking_error_weighted(n)

        # NaN/Inf guard — scan all numeric arrays
        actions_nan = int(np.isnan(self.t.actions).sum())
        actions_inf = int(np.isinf(self.t.actions).sum())
        qpos_nan = int(np.isnan(self.t.qpos).sum())
        qpos_inf = int(np.isinf(self.t.qpos).sum())
        effort_nan = int(np.isnan(self.t.effort).sum())
        effort_inf = int(np.isinf(self.t.effort).sum())
        qvel_nan = int(np.isnan(self.t.qvel).sum())
        qvel_inf = int(np.isinf(self.t.qvel).sum())

        # Per-dimension health: zero-variance + MAD-based outlier detection
        dim_health_records = self._compute_dim_health()

        return L3V2Features(
            t_rel=t_rel,
            dt=dt,
            fps=fps,
            duration=duration,
            declared_fps=self.declared_fps,
            manifest_frame_count=self.manifest_frame_count,
            joint_action_delta_norm=joint_action_delta_norm,
            joint_state_delta_norm=joint_state_delta_norm,
            action_delta_arm_norm=action_delta_arm_norm,
            action_delta_hand_norm=action_delta_hand_norm,
            state_delta_arm_norm=state_delta_arm_norm,
            state_delta_hand_norm=state_delta_hand_norm,
            joint_acc_norm=joint_acc_norm,
            joint_jerk_norm=joint_jerk_norm,
            action_delta2_norm=action_delta2_norm,
            oscillation_strength=oscillation,
            chatter_strength=chatter,
            tracking_error_weighted=tracking,
            sync_valid=sync_valid_arr,
            sync_diff_sec=sync_diff_sec_arr,
            dt_jitter_cv=jitter_cv,
            depth_dt=depth_dt,
            actions_nan=actions_nan,
            actions_inf=actions_inf,
            qpos_nan=qpos_nan,
            qpos_inf=qpos_inf,
            effort_nan=effort_nan,
            effort_inf=effort_inf,
            qvel_nan=qvel_nan,
            qvel_inf=qvel_inf,
            dim_health_records=dim_health_records,
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

    def _oscillation_strength_arm(self, target_n: int) -> np.ndarray:
        aa = self.t.actions_arm
        out = np.zeros(target_n, dtype=np.float64)
        if aa.shape[0] < 3 or aa.shape[1] == 0:
            return out
        delta = np.diff(aa, axis=0)
        abs_delta = np.abs(delta)
        pct = self.p.get('fe_osc_pct', 10)
        eps = np.maximum(np.nanpercentile(abs_delta, pct, axis=0), 1e-4)
        valid = (abs_delta[1:] > eps) & (abs_delta[:-1] > eps)
        signs = np.sign(delta)
        reversals = (signs[1:] * signs[:-1]) < 0
        effective_rev = reversals & valid
        amp = (abs_delta[1:] + abs_delta[:-1]) * 0.5
        weighted = effective_rev.astype(np.float64) * amp
        out[2:] = np.nanmean(weighted, axis=1)
        return out

    def _chatter_strength_hand(self, target_n: int) -> np.ndarray:
        ah = self.t.actions_hand
        out = np.zeros(target_n, dtype=np.float64)
        if ah.shape[0] < 3 or ah.shape[1] == 0:
            return out
        delta = np.diff(ah, axis=0)
        abs_delta = np.abs(delta)
        pct = self.p.get('fe_chat_pct', 10)
        eps = np.maximum(np.nanpercentile(abs_delta, pct, axis=0), 1e-4)
        valid = (abs_delta[1:] > eps) & (abs_delta[:-1] > eps)
        signs = np.sign(delta)
        reversals = (signs[1:] * signs[:-1]) < 0
        effective_chatter = reversals & valid
        out[2:] = np.nanmean(effective_chatter.astype(float), axis=1)
        return out

    def _tracking_error_weighted(self, target_n: int) -> np.ndarray:
        out = np.zeros(target_n, dtype=np.float64)
        arm_err = np.zeros(target_n, dtype=np.float64)
        hand_err = np.zeros(target_n, dtype=np.float64)
        if self.t.actions_arm.shape[1] and self.t.qpos_arm.shape[1]:
            arm_err = np.nanmean(np.abs(self.t.actions_arm - self.t.qpos_arm), axis=1)
        if self.t.actions_hand.shape[1] and self.t.qpos_hand.shape[1]:
            hand_err = np.nanmean(np.abs(self.t.actions_hand - self.t.qpos_hand), axis=1)
        w_arm = self.p.get('dx01_arm_weight', 0.7)
        w_hand = self.p.get('dx01_hand_weight', 0.3)
        if self.t.actions_arm.shape[1] and self.t.actions_hand.shape[1]:
            out = w_arm * arm_err + w_hand * hand_err
        elif self.t.actions_arm.shape[1]:
            out = arm_err
        elif self.t.actions_hand.shape[1]:
            out = hand_err
        return out

    def _compute_dim_health(self) -> list[dict]:
        """Per-dimension health: zero-variance (all dims) + MAD-based outlier detection (position/action only)."""
        records: list[dict] = []
        sources = [
            ('arm_qpos', self.t.qpos_arm),
            ('arm_actions', self.t.actions_arm),
            ('arm_effort', self.t.effort_arm),
            ('arm_qvel', self.t.qvel_arm),
            ('hand_qpos', self.t.qpos_hand),
            ('hand_actions', self.t.actions_hand),
        ]
        # Only run outlier detection on arm position/action signals;
        # hand joints naturally jump (open↔close) and qvel/effort spiking is normal.
        outlier_sources = {'arm_qpos', 'arm_actions'}
        has_hand = self.t.actions_hand.ndim == 2 and self.t.actions_hand.shape[1] > 0
        if not has_hand:
            sources = [s for s in sources if not s[0].startswith('hand_')]

        for cat, arr in sources:
            if arr.ndim < 2 or arr.shape[1] == 0 or arr.shape[0] == 0:
                continue
            n_frames, n_dims = arr.shape
            do_outlier = cat in outlier_sources
            for d in range(n_dims):
                dim_vals = arr[:, d].astype(np.float64)
                std = float(np.std(dim_vals))
                if std == 0:
                    records.append({
                        'label': f'{cat}_dim_{d}',
                        'category': cat,
                        'dim_index': d,
                        'n_frames': n_frames,
                        'std': 0.0,
                        'is_zero_variance': True,
                        'outlier_count': 0,
                        'outlier_ratio': 0.0,
                    })
                    continue
                if not do_outlier:
                    records.append({
                        'label': f'{cat}_dim_{d}',
                        'category': cat,
                        'dim_index': d,
                        'n_frames': n_frames,
                        'std': std,
                        'is_zero_variance': False,
                        'outlier_count': 0,
                        'outlier_ratio': 0.0,
                    })
                    continue
                median = float(np.median(dim_vals))
                mad = float(np.median(np.abs(dim_vals - median)))
                if mad < 1e-10:
                    mad = 1e-10
                robust_z = 0.6745 * np.abs(dim_vals - median) / mad
                outlier_count = int((robust_z > 10).sum())
                records.append({
                    'label': f'{cat}_dim_{d}',
                    'category': cat,
                    'dim_index': d,
                    'n_frames': n_frames,
                    'std': std,
                    'is_zero_variance': False,
                    'outlier_count': outlier_count,
                    'outlier_ratio': float(outlier_count / max(n_frames, 1)),
                })
        return records
