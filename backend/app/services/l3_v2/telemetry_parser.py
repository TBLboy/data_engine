from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class ParsedTelemetry:
    timestamps: np.ndarray
    t_rel: np.ndarray
    qpos: np.ndarray
    qvel: np.ndarray
    actions: np.ndarray
    effort: np.ndarray
    sync_valid: np.ndarray
    sync_diff_ms: np.ndarray
    arm_dims: list[int]
    hand_dims: list[int]
    qpos_arm: np.ndarray
    qpos_hand: np.ndarray
    qvel_arm: np.ndarray
    actions_arm: np.ndarray
    actions_hand_raw: np.ndarray
    actions_hand: np.ndarray
    effort_arm: np.ndarray
    ee_poses_qpos_left: np.ndarray | None = None
    ee_poses_qpos_right: np.ndarray | None = None
    ee_poses_actions_left: np.ndarray | None = None
    ee_poses_actions_right: np.ndarray | None = None

    @property
    def n(self) -> int:
        return int(self.t_rel.shape[0])

    @property
    def duration(self) -> float:
        return float(self.t_rel[-1]) if self.t_rel.size else 0.0

    @property
    def fps(self) -> float:
        if self.n <= 1 or self.duration <= 1e-9:
            return 0.0
        return float(self.n / self.duration)


class TelemetryParser:
    """Normalize TeleDex telemetry.npz into a stable in-memory representation."""

    def __init__(self, telemetry: dict[str, Any]):
        self.telemetry = telemetry

    def _get_required(self, key: str) -> np.ndarray:
        value = self.telemetry[key]
        return np.asarray(value)

    def _get_optional(self, key: str) -> np.ndarray | None:
        if key not in self.telemetry:
            return None
        value = np.asarray(self.telemetry[key])
        return value.astype(np.float64) if value.size else None

    def parse(self, dof_config: dict[str, int] | None = None, arm_mode: str = 'both_arms') -> ParsedTelemetry:
        ts = self._get_required('timestamps').astype(np.float64)
        qpos = self._get_required('qpos').astype(np.float64)
        qvel = self._get_required('qvel').astype(np.float64)
        actions = self._get_required('actions').astype(np.float64)
        effort = self._get_required('effort').astype(np.float64)
        t_rel = ts - ts[0] if ts.size else ts

        sync_valid = np.asarray(self.telemetry.get('sync_validation_is_valid', np.ones(len(ts), dtype=bool))).astype(bool)
        sync_diff_ms = np.asarray(self.telemetry.get('sync_validation_max_diff', np.zeros(len(ts), dtype=np.float64))).astype(np.float64)

        if qpos.ndim != 2:
            qpos = qpos.reshape((len(ts), -1))
        if qvel.ndim != 2:
            qvel = qvel.reshape((len(ts), -1))
        if actions.ndim != 2:
            actions = actions.reshape((len(ts), -1))
        if effort.ndim != 2:
            effort = effort.reshape((len(ts), -1))

        if not dof_config:
            raise ValueError('dof_config is required — read from metadata.json device.arm/hand.joints')
        arm_left = dof_config.get('arm_left_dof', 7)
        arm_right = dof_config.get('arm_right_dof', 7)
        hand_left = dof_config.get('hand_left_dof', 6)
        hand_right = dof_config.get('hand_right_dof', 6)
        arm_total = arm_left + arm_right
        hand_total = hand_left + hand_right
        left_arm_dims = list(range(0, arm_left))
        right_arm_dims = list(range(arm_left, arm_total))
        left_hand_dims = list(range(arm_total, arm_total + hand_left))
        right_hand_dims = list(range(arm_total + hand_left, arm_total + hand_total))

        if arm_mode == 'left_arm':
            arm_dims = left_arm_dims
            hand_dims = left_hand_dims
        elif arm_mode == 'right_arm':
            arm_dims = right_arm_dims
            hand_dims = right_hand_dims
        else:
            arm_dims = left_arm_dims + right_arm_dims
            hand_dims = left_hand_dims + right_hand_dims

        qpos_arm = qpos[:, arm_dims] if arm_dims else np.zeros((len(ts), 0), dtype=np.float64)
        qpos_hand_raw = qpos[:, hand_dims] if hand_dims else np.zeros((len(ts), 0), dtype=np.float64)
        qvel_arm = qvel[:, arm_dims] if arm_dims else np.zeros((len(ts), 0), dtype=np.float64)
        actions_arm = actions[:, arm_dims] if arm_dims else np.zeros((len(ts), 0), dtype=np.float64)
        actions_hand_raw = actions[:, hand_dims] if hand_dims else np.zeros((len(ts), 0), dtype=np.float64)
        effort_arm = effort[:, arm_dims] if arm_dims else np.zeros((len(ts), 0), dtype=np.float64)

        return ParsedTelemetry(
            timestamps=ts,
            t_rel=t_rel,
            qpos=qpos,
            qvel=qvel,
            actions=actions,
            effort=effort,
            sync_valid=sync_valid,
            sync_diff_ms=sync_diff_ms,
            arm_dims=arm_dims,
            hand_dims=hand_dims,
            qpos_arm=qpos_arm,
            # Hand raw→normalized: 0-255 range division (Linker Hand hardware spec, see requirements.md)
            qpos_hand=qpos_hand_raw / 255.0 if hand_dims else np.zeros((len(ts), 0), dtype=np.float64),
            qvel_arm=qvel_arm,
            actions_arm=actions_arm,
            actions_hand_raw=actions_hand_raw,
            actions_hand=actions_hand_raw / 255.0 if hand_dims else np.zeros((len(ts), 0), dtype=np.float64),
            effort_arm=effort_arm,
            ee_poses_qpos_left=self._get_optional('ee_poses_qpos_left'),
            ee_poses_qpos_right=self._get_optional('ee_poses_qpos_right'),
            ee_poses_actions_left=self._get_optional('ee_poses_actions_left'),
            ee_poses_actions_right=self._get_optional('ee_poses_actions_right'),
        )
