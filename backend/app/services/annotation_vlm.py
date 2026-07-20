"""VLM prompt/parse helpers for fixed Sub Goal occurrence coarse alignment."""

from __future__ import annotations

import json
import re
from typing import Any

from app.models import SubGoalDefinition
from app.services.annotation import (
    INSTANCE_STATUSES,
    NO_RANGE_INSTANCE_STATUSES,
    RANGED_INSTANCE_STATUSES,
    TASK_OUTCOMES,
)


FRAME_SAMPLER_VERSION = 'uniform-steps-v1+minio-rgb-ffmpeg-v1'
PROMPT_VERSION = 'subgoal-occurrence-v6'

_TASK_OUTCOME_ALIASES = {
    'success': 'completed_normally',
    'completed': 'completed_normally',
    'completed_normally': 'completed_normally',
    'completed_with_retry': 'completed_with_retry',
    'retry': 'completed_with_retry',
    'partial': 'partially_completed',
    'partially_completed': 'partially_completed',
    'failure': 'failed',
    'failed': 'failed',
    'fail': 'failed',
    'unknown': 'uncertain',
    'uncertain': 'uncertain',
}


def uniform_sample_steps(frame_count: int, *, max_samples: int = 12) -> list[int]:
    """Return inclusive step indices for coarse timeline anchoring."""
    if frame_count is None or frame_count <= 0:
        return []
    n = max(1, min(max_samples, frame_count))
    if n == 1:
        return [0]
    if frame_count == 1:
        return [0]
    steps = sorted({int(round(i * (frame_count - 1) / (n - 1))) for i in range(n)})
    return [s for s in steps if 0 <= s < frame_count]


def definition_prompt_rows(definitions: list[SubGoalDefinition]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in sorted(definitions, key=lambda d: d.sequence_no):
        rows.append({
            'sequenceNo': item.sequence_no,
            'code': item.code,
            'nameEn': item.name_en,
            'nameZh': item.name_zh,
            'description': item.description or '',
            'actionVerb': item.action_verb or '',
            'isRequired': bool(item.is_required),
            'isConditional': bool(item.is_conditional),
            'maxOccurrences': item.max_occurrences,
        })
    return rows


def build_generation_prompt(
    *,
    job_type: str,
    task_description: str,
    schema_id: str,
    schema_version: int,
    definitions: list[SubGoalDefinition],
    frame_count: int,
    sample_steps: list[int],
    media_frame_steps: list[int] | None = None,
    media_camera: str | None = None,
) -> str:
    # Keep prompt short: long schema dumps make thinking VLMs exhaust num_predict on prose.
    def_rows = []
    for item in sorted(definitions, key=lambda d: d.sequence_no):
        def_rows.append({
            'code': item.code,
            'nameEn': item.name_en,
            'max': item.max_occurrences,
            'required': bool(item.is_required),
        })
    outcomes = ','.join(sorted(TASK_OUTCOMES))
    statuses = ','.join(sorted(INSTANCE_STATUSES))
    codes = [item.code for item in sorted(definitions, key=lambda d: d.sequence_no)]
    fc = int(frame_count or 0)
    task_hint = (task_description or '').strip()
    media_steps = media_frame_steps or []
    media_line = (
        f'camera={media_camera or "none"}; image_steps={media_steps} (images attached in order)'
        if media_steps
        else 'no_images=true'
    )
    example_code = codes[0] if codes else 'reach_object'
    # job_type/schema kept for audit; omit verbose field lectures.
    _ = (job_type, schema_id, schema_version, sample_steps)
    return (
        'Output one JSON object only (no prose, no markdown).\n'
        f'task={task_hint}\n'
        f'frame_count={fc}\n'
        f'{media_line}\n'
        f'definitions={json.dumps(def_rows, ensure_ascii=False)}\n'
        f'taskOutcome in [{outcomes}]\n'
        f'occurrence status in [{statuses}]\n'
        f'definitionCode in {codes}\n'
        'Shape:\n'
        f'{{"canonicalInstructionEn":"Collect one radish.",'
        f'"canonicalInstructionZh":"采集一根萝卜",'
        f'"taskOutcome":"completed_normally",'
        f'"annotationSchemaVersion":"1.0",'
        f'"occurrences":[{{"definitionCode":"{example_code}","occurrenceNo":1,'
        f'"status":"observed","startStep":0,"endStepExclusive":10,'
        f'"representativeStep":5,"failureReason":null,"notes":null}}]}}\n'
        'Rules: short imperative instruction; continuous occurrenceNo from 1; '
        f'for observed/failed use 0<=start<end<={fc} and rep in range; '
        'weak evidence -> not_observed + null steps; no invented codes.\n'
    )


def parse_vlm_payload(text: str) -> dict[str, Any]:
    """Best-effort structured parse of free-form VLM text."""
    if not text:
        return {}
    stripped = text.strip()
    candidates: list[str] = [stripped]
    fenced = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', stripped, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1))
    # Prefer objects that look like our schema (instruction/occurrences), not prose wrappers.
    marker_hits = list(
        re.finditer(
            r'\{\s*"(?:canonicalInstructionEn|canonical_instruction_en|occurrences|taskOutcome|task_outcome)"',
            stripped,
        )
    )
    for match in marker_hits:
        start = match.start()
        # Balanced brace extract from this marker.
        depth = 0
        end = -1
        for i, ch in enumerate(stripped[start:], start=start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end > start:
            candidates.append(stripped[start : end + 1])
    # Fallback: first '{' to last '}'.
    if '{' in stripped and '}' in stripped:
        start = stripped.find('{')
        end = stripped.rfind('}')
        if end > start:
            candidates.append(stripped[start : end + 1])
    # Nested JSON string payloads (thinking models sometimes wrap once).
    for blob in list(candidates):
        if blob.startswith('{') and '"canonicalInstructionEn"' in blob and '\\"' in blob:
            try:
                inner = json.loads(blob)
                if isinstance(inner, dict):
                    for key in ('canonicalInstructionEn', 'content', 'text'):
                        nested = inner.get(key)
                        if isinstance(nested, str) and nested.strip().startswith('{'):
                            candidates.append(nested.strip())
            except Exception:
                pass

    def _score(parsed: dict[str, Any]) -> int:
        score = 0
        instr = parsed.get('canonicalInstructionEn') or parsed.get('canonical_instruction_en')
        if isinstance(instr, str) and instr.strip():
            score += 3
            # Prefer short real instructions over schema echo / reasoning.
            if len(instr.strip()) <= 120 and 'we are given' not in instr.lower():
                score += 2
        occ = parsed.get('occurrences') or parsed.get('subGoals')
        if isinstance(occ, list):
            score += 2 + min(len(occ), 5)
        if parsed.get('taskOutcome') or parsed.get('task_outcome'):
            score += 1
        return score

    best: dict[str, Any] | None = None
    best_score = -1
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        # Unwrap one level if the model nested JSON as a string field.
        for key in ('canonicalInstructionEn', 'content', 'text', 'result'):
            nested = parsed.get(key)
            if isinstance(nested, str):
                nested_stripped = nested.strip()
                if nested_stripped.startswith('{') and nested_stripped.endswith('}'):
                    try:
                        nested_obj = json.loads(nested_stripped)
                        if isinstance(nested_obj, dict) and (
                            'canonicalInstructionEn' in nested_obj or 'occurrences' in nested_obj
                        ):
                            parsed = nested_obj
                            break
                    except Exception:
                        pass
        if not any(
            key in parsed
            for key in (
                'canonicalInstructionEn',
                'canonical_instruction_en',
                'occurrences',
                'subGoals',
                'taskOutcome',
                'task_outcome',
            )
        ):
            continue
        score = _score(parsed)
        if score > best_score:
            best = parsed
            best_score = score
    if best is not None:
        return best
    return {'occurrences': []}


def normalize_task_outcome(value: Any) -> str | None:
    if value is None:
        return None
    key = str(value).strip().lower().replace(' ', '_').replace('-', '_')
    mapped = _TASK_OUTCOME_ALIASES.get(key) or _TASK_OUTCOME_ALIASES.get(str(value).strip())
    if mapped in TASK_OUTCOMES:
        return mapped
    if str(value).strip() in TASK_OUTCOMES:
        return str(value).strip()
    return None


def normalize_occurrences(
    raw_occurrences: Any,
    *,
    definitions: list[SubGoalDefinition],
    frame_count: int,
) -> list[dict[str, Any]]:
    """Validate/clamp VLM occurrences to the frozen schema and episode bounds."""
    if not isinstance(raw_occurrences, list):
        return []
    by_code = {item.code: item for item in definitions}
    by_id = {item.id: item for item in definitions}
    accepted: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for raw in raw_occurrences:
        if not isinstance(raw, dict):
            continue
        code = str(raw.get('definitionCode') or raw.get('definition_code') or raw.get('code') or '').strip()
        definition_id = str(raw.get('definitionId') or raw.get('sub_goal_definition_id') or '').strip()
        definition = by_code.get(code) or by_id.get(definition_id)
        if definition is None:
            continue
        try:
            occurrence_no = int(raw.get('occurrenceNo', raw.get('occurrence_no', 0)))
        except Exception:
            continue
        if occurrence_no < 1:
            continue
        key = (definition.id, occurrence_no)
        if key in seen:
            continue
        status = str(raw.get('status') or 'observed').strip()
        if status not in INSTANCE_STATUSES:
            continue
        start = _optional_int(raw.get('startStep', raw.get('start_step')))
        end = _optional_int(raw.get('endStepExclusive', raw.get('end_step_exclusive')))
        rep = _optional_int(raw.get('representativeStep', raw.get('representative_step')))
        failure_reason = raw.get('failureReason', raw.get('failure_reason'))
        notes = raw.get('notes')
        if status in RANGED_INSTANCE_STATUSES:
            if frame_count <= 0:
                # Keep semantic status but drop invalid ranges when timeline unknown.
                start = end = rep = None
                if status == 'observed':
                    status = 'uncertain'
            else:
                if start is None or end is None:
                    continue
                start = max(0, min(start, frame_count - 1))
                end = max(start + 1, min(end, frame_count))
                if rep is None:
                    rep = start
                rep = max(start, min(rep, end - 1))
            if status == 'failed' and not (str(failure_reason or '').strip()):
                failure_reason = 'vlm_reported_failure'
        elif status in NO_RANGE_INSTANCE_STATUSES:
            start = end = rep = None
        elif status == 'uncertain':
            # Allow either null range or clamped range.
            if start is not None and end is not None and frame_count > 0:
                start = max(0, min(start, frame_count - 1))
                end = max(start + 1, min(end, frame_count))
                if rep is None:
                    rep = start
                rep = max(start, min(rep, end - 1))
            else:
                start = end = rep = None
        seen.add(key)
        accepted.append({
            'definitionId': definition.id,
            'definitionCode': definition.code,
            'occurrenceNo': occurrence_no,
            'status': status,
            'startStep': start,
            'endStepExclusive': end,
            'representativeStep': rep,
            'failureReason': str(failure_reason).strip() if failure_reason else None,
            'notes': str(notes).strip() if notes else None,
            'source': 'vlm_initial',
        })
    # Cap by max_occurrences per definition.
    counts: dict[str, int] = {}
    limited: list[dict[str, Any]] = []
    for item in sorted(accepted, key=lambda x: (x['definitionCode'], x['occurrenceNo'])):
        definition = by_id[item['definitionId']]
        used = counts.get(definition.id, 0)
        if definition.max_occurrences is not None and used >= definition.max_occurrences:
            continue
        counts[definition.id] = used + 1
        limited.append(item)
    return limited


def _optional_int(value: Any) -> int | None:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except Exception:
        return None
