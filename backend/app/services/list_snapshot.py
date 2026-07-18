from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.services.scan_v3_types import EpisodeSnapshot, ListSnapshot, ObjectSnapshot


EPISODE_PATTERN = re.compile(r'^episode_[0-9a-zA-Z_-]{1,33}$')
SELECTIVE_ROLES = {
    'manifest', 'metadata', 'telemetry_npz', 'camera_info',
    'camera_rgb_video', 'camera_depth_video', 'camera_depth_colormap_video',
    'camera_aux_video', 'timestamp_npy', 'recording_info', 'device_info',
    'raw_metadata_yaml', 'raw_mcap',
}


def classify_object_role(object_scope: str, relative_key: str) -> str:
    normalized = relative_key.lower()
    if object_scope == 'processed':
        if normalized == 'manifest.json':
            return 'manifest'
        if normalized == 'metadata.json':
            return 'metadata'
        if normalized == 'telemetry.npz':
            return 'telemetry_npz'
        if normalized == 'camera_info.json':
            return 'camera_info'
        if normalized.startswith('cameras/') and normalized.endswith('.mp4'):
            if 'depth' in normalized and 'colormap' in normalized:
                return 'camera_depth_colormap_video'
            if 'depth' in normalized:
                return 'camera_depth_video'
            if 'rgb' in normalized or normalized.endswith(('cam_top.mp4', 'cam_left_wrist.mp4', 'cam_right_wrist.mp4')):
                return 'camera_rgb_video'
            if 'left' in normalized or 'right' in normalized:
                return 'camera_aux_video'
        if normalized.endswith('.npy') and ('timestamp' in normalized or 'sync' in normalized):
            return 'timestamp_npy'
        if normalized.endswith('.png') and ('depth' in normalized or 'frame' in normalized):
            return 'bulk_depth_frame'
        if normalized.endswith('.ply'):
            return 'bulk_pointcloud_frame'
        return 'unknown'

    if normalized == 'recording_info.json':
        return 'recording_info'
    if normalized == 'device_info.json':
        return 'device_info'
    if normalized == 'metadata.yaml':
        return 'raw_metadata_yaml'
    if normalized.endswith('.mcap'):
        return 'raw_mcap'
    return 'unknown'


def _modified_text(value: datetime | None) -> str:
    if value is None:
        return ''
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds')


@dataclass(slots=True)
class _ScopeAccumulator:
    hasher: object = field(default_factory=hashlib.sha256)
    count: int = 0
    total_size: int = 0
    last_key: str = ''

    def add(self, *, object_key: str, etag: str, size: int, last_modified: datetime | None) -> None:
        if self.last_key and object_key < self.last_key:
            raise ValueError('MinIO object enumeration is not lexicographically ordered')
        self.last_key = object_key
        payload = json.dumps(
            [object_key, etag, size, _modified_text(last_modified)],
            ensure_ascii=True,
            separators=(',', ':'),
        ).encode('utf-8')
        self.hasher.update(len(payload).to_bytes(8, 'big'))
        self.hasher.update(payload)
        self.count += 1
        self.total_size += size

    @property
    def fingerprint(self) -> str:
        return self.hasher.hexdigest() if self.count else ''


@dataclass(slots=True)
class _EpisodeAccumulator:
    episode_name: str
    raw_prefix: str = ''
    processed_prefix: str = ''
    raw: _ScopeAccumulator = field(default_factory=_ScopeAccumulator)
    processed: _ScopeAccumulator = field(default_factory=_ScopeAccumulator)
    objects: list[ObjectSnapshot] = field(default_factory=list)
    latest_modified: datetime | None = None


def _read_json_object(service, bucket: str, object_key: str) -> dict:
    response = service.get_object(bucket, object_key)
    try:
        payload = json.loads(response.read().decode('utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('JSON object must contain a mapping')
        return payload
    finally:
        response.close()
        response.release_conn()


def build_list_snapshot(
    service,
    bucket: str,
    list_prefix: str,
    *,
    existing_fingerprints: dict[str, tuple[str, str]] | None = None,
    range_start: str = '',
    range_end: str = '',
) -> ListSnapshot:
    started_at = datetime.utcnow()
    prefix = f'{list_prefix.strip("/")}/' if list_prefix.strip('/') else ''
    accumulators: dict[str, _EpisodeAccumulator] = {}
    object_count = 0

    for item in service.list_objects(bucket, prefix=prefix, recursive=True):
        object_key = str(getattr(item, 'object_name', '') or '')
        if not object_key or object_key.endswith('/') or not object_key.startswith(prefix):
            continue
        relative = object_key[len(prefix):]
        parts = relative.split('/')
        if len(parts) < 3 or parts[0] not in {'raw', 'processed'} or not EPISODE_PATTERN.fullmatch(parts[1]):
            continue
        scope, episode_name = parts[0], parts[1]
        if range_start and episode_name < range_start:
            continue
        if range_end and episode_name >= range_end:
            continue

        episode = accumulators.setdefault(episode_name, _EpisodeAccumulator(episode_name=episode_name))
        episode_prefix = f'{prefix}{scope}/{episode_name}/'
        if scope == 'raw':
            episode.raw_prefix = episode_prefix
        else:
            episode.processed_prefix = episode_prefix
        size = int(getattr(item, 'size', 0) or 0)
        etag = str(getattr(item, 'etag', '') or '').strip('"')
        modified = getattr(item, 'last_modified', None)
        accumulator = episode.raw if scope == 'raw' else episode.processed
        accumulator.add(object_key=object_key, etag=etag, size=size, last_modified=modified)
        object_count += 1
        if modified is not None and (episode.latest_modified is None or modified > episode.latest_modified):
            episode.latest_modified = modified

        role = classify_object_role(scope, '/'.join(parts[2:]))
        if role in SELECTIVE_ROLES:
            episode.objects.append(ObjectSnapshot(
                object_key=object_key,
                object_scope=scope,
                object_role=role,
                size_bytes=size,
                content_hash=etag,
                last_modified=modified,
            ))

    snapshots: list[EpisodeSnapshot] = []
    known = existing_fingerprints or {}
    for episode_name in sorted(accumulators):
        episode = accumulators[episode_name]
        raw_fingerprint = episode.raw.fingerprint
        processed_fingerprint = episode.processed.fingerprint
        changed = known.get(episode_name) != (raw_fingerprint, processed_fingerprint)
        manifest = None
        manifest_error = ''
        manifest_object = next((item for item in episode.objects if item.object_role == 'manifest'), None)
        if changed and manifest_object is not None:
            try:
                manifest = _read_json_object(service, bucket, manifest_object.object_key)
            except Exception as exc:
                manifest_error = f'{type(exc).__name__}: {exc}'[:500]
        if changed and manifest_error:
            raise RuntimeError(f'manifest read failed for {episode_name}: {manifest_error}')

        snapshots.append(EpisodeSnapshot(
            episode_name=episode_name,
            raw_prefix=episode.raw_prefix,
            processed_prefix=episode.processed_prefix,
            raw_object_count=episode.raw.count,
            processed_object_count=episode.processed.count,
            raw_total_size_bytes=episode.raw.total_size,
            processed_total_size_bytes=episode.processed.total_size,
            raw_content_fingerprint=raw_fingerprint,
            processed_content_fingerprint=processed_fingerprint,
            latest_object_modified_at=episode.latest_modified,
            selective_objects=tuple(sorted(episode.objects, key=lambda item: item.object_key)),
            manifest=manifest,
            manifest_error=manifest_error,
        ))

    return ListSnapshot(
        bucket=bucket,
        list_prefix=prefix,
        episodes=tuple(snapshots),
        object_count=object_count,
        enumeration_complete=True,
        started_at=started_at,
        finished_at=datetime.utcnow(),
        range_start=range_start,
        range_end=range_end,
    )
