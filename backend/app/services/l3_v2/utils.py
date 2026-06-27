from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    level: str
    label: str
    sourceMetricId: str
    sourceEvidenceId: str
    qualityDimension: str
    rawValue: float | None = None
    threshold: float | None = None
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            'start': round(float(self.start), 3),
            'end': round(float(self.end), 3),
            'startSec': round(float(self.start), 3),
            'endSec': round(float(self.end), 3),
            'level': self.level,
            'label': self.label,
            'sourceMetricId': self.sourceMetricId,
            'sourceEvidenceId': self.sourceEvidenceId,
            'qualityDimension': self.qualityDimension,
            'rawValue': None if self.rawValue is None else round(float(self.rawValue), 6),
            'threshold': None if self.threshold is None else round(float(self.threshold), 6),
            'confidence': round(float(self.confidence), 3),
        }


def safe_mean(arr: np.ndarray, default: float = 0.0) -> float:
    if arr.size == 0:
        return default
    value = float(np.nanmean(arr))
    return value if np.isfinite(value) else default


def safe_percentile(arr: np.ndarray, q: float, default: float = 0.0) -> float:
    if arr.size == 0:
        return default
    value = float(np.nanpercentile(arr, q))
    return value if np.isfinite(value) else default


def clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, float(value)))


def level_from_score(score: float) -> str:
    if score >= 7.5:
        return 'good'
    if score >= 5.0:
        return 'warn'
    return 'bad'


def score_inverse(value: float, good: float, warn: float, bad: float | None = None) -> float:
    """Map a lower-is-better value to a 0-10 score.

    good: value at or below this threshold scores 10.
    warn: value around this threshold scores 5.
    bad: value at or above this threshold scores 0. If absent, use 2*warn-good.
    """
    if bad is None:
        bad = warn + max(warn - good, 1e-9)
    value = float(value)
    if value <= good:
        return 10.0
    if value >= bad:
        return 0.0
    if value <= warn:
        return 10.0 - 5.0 * (value - good) / max(warn - good, 1e-9)
    return 5.0 - 5.0 * (value - warn) / max(bad - warn, 1e-9)


def score_ratio(value: float, good: float, warn: float, bad: float | None = None) -> float:
    """Map a higher-is-better ratio/value to a 0-10 score."""
    if bad is None:
        bad = max(0.0, warn - (good - warn))
    value = float(value)
    if value >= good:
        return 10.0
    if value <= bad:
        return 0.0
    if value >= warn:
        return 5.0 + 5.0 * (value - warn) / max(good - warn, 1e-9)
    return 5.0 * (value - bad) / max(warn - bad, 1e-9)


def mask_to_segments(
    mask: np.ndarray,
    t_rel: np.ndarray,
    *,
    label: str,
    level: str,
    source_metric_id: str,
    source_evidence_id: str,
    quality_dimension: str,
    min_dur: float = 0.5,
    gap_merge: float = 0.3,
    raw_values: np.ndarray | None = None,
    threshold: float | None = None,
    confidence: float = 1.0,
) -> list[dict]:
    """Convert a frame mask into explainable timeline segments.

    Keeps sub-second precision for L3 v2 while remaining compatible with the
    legacy front-end, because start/end still exist.
    """
    if mask.size == 0 or t_rel.size == 0 or not np.any(mask):
        return []

    raw_segments: list[Segment] = []
    start_idx: int | None = None
    bools = mask.astype(bool).tolist()
    for i, flag in enumerate(bools):
        if flag and start_idx is None:
            start_idx = i
        if (not flag or i == len(bools) - 1) and start_idx is not None:
            end_idx = i if flag and i == len(bools) - 1 else max(start_idx, i - 1)
            start = float(t_rel[start_idx])
            end = float(t_rel[end_idx])
            if end < start:
                end = start
            if raw_values is not None and raw_values.size:
                rv = safe_percentile(raw_values[start_idx:end_idx + 1], 95, None)  # type: ignore[arg-type]
            else:
                rv = None
            raw_segments.append(Segment(
                start=start,
                end=end,
                level=level,
                label=label,
                sourceMetricId=source_metric_id,
                sourceEvidenceId=source_evidence_id,
                qualityDimension=quality_dimension,
                rawValue=rv,
                threshold=threshold,
                confidence=confidence,
            ))
            start_idx = None

    if not raw_segments:
        return []

    merged: list[Segment] = []
    for seg in sorted(raw_segments, key=lambda s: (s.label, s.start, s.end)):
        if not merged:
            merged.append(seg)
            continue
        cur = merged[-1]
        if (
            cur.label == seg.label
            and cur.level == seg.level
            and cur.sourceMetricId == seg.sourceMetricId
            and seg.start <= cur.end + gap_merge
        ):
            merged[-1] = Segment(
                start=cur.start,
                end=max(cur.end, seg.end),
                level=cur.level,
                label=cur.label,
                sourceMetricId=cur.sourceMetricId,
                sourceEvidenceId=cur.sourceEvidenceId,
                qualityDimension=cur.qualityDimension,
                rawValue=max(
                    cur.rawValue if cur.rawValue is not None else float('-inf'),
                    seg.rawValue if seg.rawValue is not None else float('-inf'),
                ) if (cur.rawValue is not None or seg.rawValue is not None) else None,
                threshold=cur.threshold,
                confidence=min(cur.confidence, seg.confidence),
            )
        else:
            merged.append(seg)

    out: list[dict] = []
    for seg in merged:
        duration = seg.end - seg.start
        if duration < min_dur:
            # Keep the segment, but mark it as at least min_dur to make it visible and clickable.
            seg = Segment(
                start=seg.start,
                end=seg.start + min_dur,
                level=seg.level,
                label=seg.label,
                sourceMetricId=seg.sourceMetricId,
                sourceEvidenceId=seg.sourceEvidenceId,
                qualityDimension=seg.qualityDimension,
                rawValue=seg.rawValue,
                threshold=seg.threshold,
                confidence=seg.confidence,
            )
        out.append(seg.to_dict())
    return sorted(out, key=lambda s: (s['startSec'], s['sourceMetricId'], s['label']))


def weighted_average(items: Iterable[tuple[float, float]]) -> float:
    pairs = [(float(v), float(w)) for v, w in items if w > 0]
    denom = sum(w for _, w in pairs)
    if denom <= 1e-12:
        return 0.0
    return sum(v * w for v, w in pairs) / denom
