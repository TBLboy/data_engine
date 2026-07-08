from __future__ import annotations

from typing import Any

import numpy as np

from .feature_extractor import FeatureExtractor
from .metric_engine import MetricEngine
from .quality_engine import QualityEngine
from .telemetry_parser import TelemetryParser


class L3V2Engine:
    """RDDQF-oriented L3 v2 MVP engine.

    The engine is intentionally side-effect free. It receives telemetry arrays and
    returns an API-ready dictionary. Result caching can be added above this layer
    without changing the computation contract.
    """

    def __init__(self, telemetry: dict[str, Any], params: dict[str, Any] | None = None, *, depth_timestamps: np.ndarray | None = None, dof_config: dict[str, int] | None = None, arm_mode: str = 'both_arms', declared_fps: float = 0.0, manifest_frame_count: int = 0):
        self.telemetry = telemetry
        self.params = params or {}
        self.depth_timestamps = depth_timestamps
        self.dof_config = dof_config
        self.arm_mode = arm_mode
        self.declared_fps = declared_fps
        self.manifest_frame_count = manifest_frame_count

    def compute(self) -> dict:
        parsed = TelemetryParser(self.telemetry).parse(dof_config=self.dof_config, arm_mode=self.arm_mode)
        features = FeatureExtractor(
            parsed, self.params,
            depth_timestamps=self.depth_timestamps,
            declared_fps=self.declared_fps,
            manifest_frame_count=self.manifest_frame_count,
        ).extract()
        metrics, timeline, diagnostics = MetricEngine(features, self.params).compute()
        report = QualityEngine(metrics, diagnostics, self.params).build_report()
        report.update({
            'telemetryProfile': {
                'frameCount': parsed.n,
                'durationSec': round(parsed.duration, 3),
                'fps': round(parsed.fps, 3),
                'declaredFps': round(self.declared_fps, 3) if self.declared_fps > 0 else None,
                'armDims': len(parsed.arm_dims),
                'handDims': len(parsed.hand_dims),
                'armDimIndices': parsed.arm_dims,
                'handDimIndices': parsed.hand_dims,
            },
            'timelineSegments': timeline,
        })
        return report
