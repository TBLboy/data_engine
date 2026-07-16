from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta

from minio.error import S3Error
from sqlalchemy.orm import Session

from app.models import AuditEvent, Batch, ClassificationRule, DiscoveredPrefix, Episode, EpisodeInventory, EpisodeObject, ListRecord, QcReviewRevision, QcTask, ScanJob, TaskType, User
from app.services.authz import require_roles
from app.services.data_assets import enqueue_batch_asset_recompute, enqueue_list_scope_recompute
from app.services.minio_client import MinioService, get_minio_service


EPISODE_PATTERN = re.compile(r'^episode_[0-9a-zA-Z_-]+$')
TIMESTAMP_SUFFIX_PATTERN = re.compile(r'([_-]?20\d{2}[-_]?\d{2}[-_]?\d{2}([_-]?\d{2}){3})$')
STATE_RANK = {
    'ingestable': 0,
    'processable': 1,
    'qc_ready': 2,
}

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _retry_minio(fn, max_retries: int = 2, base_delay: float = 3.0):
    """MinIO 调用加重试，网络抖动时自动恢复."""
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except S3Error as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = base_delay * (attempt + 1)
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def _read_json_object(service: MinioService, bucket: str, object_key: str) -> dict:
    response = _retry_minio(lambda: service.get_object(bucket, object_key))
    try:
        return json.loads(response.read().decode('utf-8'))
    finally:
        response.close()
        response.release_conn()


def _extract_manifest_metrics(manifest: dict) -> tuple[float, int]:
    try:
        duration_sec = float(manifest.get('duration', 0.0) or 0.0)
    except (TypeError, ValueError):
        duration_sec = 0.0
    try:
        frame_count = int(manifest.get('frame_count', 0) or 0)
    except (TypeError, ValueError):
        frame_count = 0
    return duration_sec, frame_count


STALE_TIMEOUT_MINUTES = 30


def _cleanup_stale_jobs(db: Session, current_bucket: str) -> None:
    """清理超过 STALE_TIMEOUT_MINUTES 仍未完成的僵尸任务."""
    cutoff = _utcnow() - timedelta(minutes=STALE_TIMEOUT_MINUTES)
    stale = db.query(ScanJob).filter(
        ScanJob.bucket == current_bucket,
        ScanJob.status.in_(['scanning', 'classifying', 'queued']),
        ScanJob.started_at < cutoff,
    ).all()
    for job in stale:
        job.status = 'failed'
        job.error_detail = f'stale: timeout after {STALE_TIMEOUT_MINUTES}min (was {job.status})'
        job.finished_at = _utcnow()
    if stale:
        db.commit()


def _prefix_depth(prefix: str) -> int:
    normalized = prefix.strip('/')
    return len([segment for segment in normalized.split('/') if segment])


def _prefix_from_parts(parts: list[str], length: int) -> str:
    if length <= 0:
        return ''
    return '/'.join(parts[:length]) + '/'


def _scan_job_id(bucket: str) -> str:
    return f"scan_{hashlib.sha1(f'{bucket}:{int(_utcnow().timestamp())}'.encode('utf-8')).hexdigest()[:16]}"


def _list_id(bucket: str, list_prefix: str) -> str:
    return f"list_{hashlib.sha1(f'{bucket}:{list_prefix}'.encode('utf-8')).hexdigest()[:16]}"


def _episode_inventory_id(bucket: str, list_prefix: str, episode_name: str) -> str:
    digest = hashlib.sha1(f'{bucket}:{list_prefix}:{episode_name}'.encode('utf-8')).hexdigest()
    return f'inv_{digest}'


def _batch_id(list_id: str) -> str:
    return f'batch_{list_id[5:]}'


def _episode_id(batch_id: str, episode_name: str) -> str:
    return f'{batch_id}_{episode_name}'


def _batch_name(list_prefix: str) -> str:
    return list_prefix.strip('/').split('/')[-1]


def _is_technical_wrapper(segment: str) -> bool:
    normalized = segment.strip().lower()
    return normalized in {'raw_data', 'processed_data', 'data'}


def _canonical_list_prefix(prefix: str) -> str:
    normalized = prefix.strip('/')
    if not normalized:
        return ''
    parts = normalized.split('/')
    if len(parts) >= 2 and _is_technical_wrapper(parts[-1]):
        return '/'.join(parts[:-1]) + '/'
    return normalized + '/'


def _ensure_task_type(db: Session, task_type_id: str, label: str) -> TaskType:
    task_type = db.query(TaskType).filter(TaskType.id == task_type_id).first()
    if task_type:
        return task_type
    task_type = TaskType(
        id=task_type_id,
        name=label,
        description=label,
    )
    db.add(task_type)
    return task_type


def _cleanup_replaced_batch(
    db: Session,
    *,
    canonical_batch_id: str,
    canonical_batch_name: str,
    legacy_batch_id: str,
    legacy_episode_id: str,
) -> None:
    legacy_episode = db.query(Episode).filter(Episode.id == legacy_episode_id).first()
    canonical_episode = db.query(Episode).filter(Episode.id == legacy_episode_id.replace(legacy_batch_id, canonical_batch_id, 1)).first()
    legacy_batch = db.query(Batch).filter(Batch.id == legacy_batch_id).first()
    if not legacy_episode or not canonical_episode or not legacy_batch:
        return
    if db.query(QcTask).filter(QcTask.batch_id == legacy_batch_id).count() > 0:
        return
    if db.query(QcReviewRevision).filter(QcReviewRevision.episode_id == legacy_episode.id).count() > 0:
        return
    inventory = db.query(EpisodeInventory).filter(EpisodeInventory.ingested_episode_id == legacy_episode.id).first()
    if inventory:
        inventory.ingested_episode_id = canonical_episode.id
    db.delete(legacy_episode)
    db.delete(legacy_batch)
    canonical_batch = db.query(Batch).filter(Batch.id == canonical_batch_id).first()
    if canonical_batch:
        canonical_batch.episode_count = db.query(Episode).filter(Episode.batch_id == canonical_batch_id).count()
        canonical_batch.name = canonical_batch_name
        enqueue_batch_asset_recompute(db, canonical_batch_id, reason='scan_sync')


def backfill_manifest_metrics(
    db: Session,
    *,
    operator: User | None = None,
    bucket: str | None = None,
) -> dict[str, int]:
    """Repair historical duration/frame_count from processed manifest.json files."""
    service = get_minio_service()
    query = (
        db.query(EpisodeInventory, Episode, EpisodeObject.object_key, ListRecord.bucket, Batch.id)
        .join(Episode, EpisodeInventory.ingested_episode_id == Episode.id)
        .join(Batch, Episode.batch_id == Batch.id)
        .join(ListRecord, EpisodeInventory.list_id == ListRecord.id)
        .join(
            EpisodeObject,
            (EpisodeObject.episode_inventory_id == EpisodeInventory.id)
            & (EpisodeObject.object_role == 'manifest'),
        )
    )
    if bucket:
        query = query.filter(ListRecord.bucket == bucket)

    stats = {
        'candidateEpisodeCount': 0,
        'repairedEpisodeCount': 0,
        'inventoryUpdatedCount': 0,
        'episodeUpdatedCount': 0,
        'manifestReadErrorCount': 0,
        'manifestZeroMetricCount': 0,
        'touchedBatchCount': 0,
    }
    touched_batch_ids: set[str] = set()

    for index, (inventory, episode, manifest_key, row_bucket, batch_id) in enumerate(
        query.order_by(EpisodeInventory.id.asc()).all(),
        start=1,
    ):
        stats['candidateEpisodeCount'] += 1
        try:
            manifest = _read_json_object(service, row_bucket, manifest_key)
            duration_sec, frame_count = _extract_manifest_metrics(manifest)
        except Exception as exc:
            stats['manifestReadErrorCount'] += 1
            logger.warning(
                '[manifest_backfill] failed bucket=%s key=%s error=%s: %s',
                row_bucket,
                manifest_key,
                type(exc).__name__,
                exc,
            )
            continue

        if duration_sec <= 0 and frame_count <= 0:
            stats['manifestZeroMetricCount'] += 1
            continue

        row_repaired = False
        if inventory.duration_sec != duration_sec or inventory.frame_count != frame_count:
            inventory.duration_sec = duration_sec
            inventory.frame_count = frame_count
            stats['inventoryUpdatedCount'] += 1
            row_repaired = True

        if episode.duration_sec != duration_sec or episode.frame_count != frame_count:
            episode.duration_sec = duration_sec
            episode.frame_count = frame_count
            stats['episodeUpdatedCount'] += 1
            row_repaired = True

        manifest_episode_id = str(manifest.get('episode_id', '') or '').strip()
        if manifest_episode_id and inventory.episode_id_from_manifest != manifest_episode_id:
            inventory.episode_id_from_manifest = manifest_episode_id

        if row_repaired:
            stats['repairedEpisodeCount'] += 1
            touched_batch_ids.add(batch_id)

        if index % 100 == 0:
            db.flush()

    for batch_id in sorted(touched_batch_ids):
        enqueue_batch_asset_recompute(db, batch_id, reason='scan_sync')
    stats['touchedBatchCount'] = len(touched_batch_ids)

    if operator:
        now = _utcnow()
        db.add(AuditEvent(
            id=f'audit_manifest_backfill_{int(now.timestamp())}',
            operator=operator.name,
            action='回填 manifest 指标',
            target=bucket or 'all_buckets',
            detail=(
                f"candidates={stats['candidateEpisodeCount']} repaired={stats['repairedEpisodeCount']} "
                f"batches={stats['touchedBatchCount']} read_errors={stats['manifestReadErrorCount']}"
            )[:500],
            time=now,
            operator_id=operator.id,
        ))

    return stats


def _normalize_classification_text(list_prefix: str) -> tuple[str, str]:
    normalized_full_prefix = list_prefix.strip('/').lower()
    basename = normalized_full_prefix.split('/')[-1] if normalized_full_prefix else ''
    basename = TIMESTAMP_SUFFIX_PATTERN.sub('', basename).strip('-_ ')
    normalized_basename = re.sub(r'[-_/]+', ' ', basename).strip()
    normalized_full_prefix = re.sub(r'[-_/]+', ' ', normalized_full_prefix).strip()
    return normalized_full_prefix, normalized_basename


def _relative_key(episode_prefix: str, object_key: str) -> str:
    if episode_prefix and object_key.startswith(episode_prefix):
        return object_key[len(episode_prefix):]
    return object_key


def _classify_object_role(object_scope: str, relative_key: str) -> str:
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
            if 'rgb' in normalized or normalized.endswith('cam_top.mp4') or normalized.endswith('cam_left_wrist.mp4') or normalized.endswith('cam_right_wrist.mp4'):
                return 'camera_rgb_video'
            if 'left' in normalized or 'right' in normalized:
                return 'camera_aux_video'
        if normalized.endswith('.npy') and ('timestamp' in normalized or 'sync' in normalized):
            return 'timestamp_npy'
        if normalized.endswith('.png') and ('depth' in normalized or 'frame' in normalized):
            return 'depth_png_frame'
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


def _derive_state(*, raw_exists: bool, processed_exists: bool, roles: list[str], manifest_data: dict | None = None) -> str:
    role_set = set(roles)
    has_manifest = 'manifest' in role_set
    has_metadata = 'metadata' in role_set
    has_telemetry = 'telemetry_npz' in role_set
    # Use manifest's declared camera files for video presence check (not filename guessing)
    if manifest_data and isinstance(manifest_data.get('files'), dict):
        cameras = manifest_data['files'].get('cameras', {})
        has_rgb_video = any(isinstance(v, dict) and 'video' in v for v in cameras.values())
    else:
        has_rgb_video = 'camera_rgb_video' in role_set
    if processed_exists and has_manifest and has_metadata and has_telemetry and has_rgb_video:
        return 'qc_ready'
    if processed_exists:
        return 'processable'
    if raw_exists:
        return 'ingestable'
    return 'ingestable'


def _apply_state_transition(existing_state: str | None, next_state: str) -> str:
    if not existing_state:
        return next_state
    return existing_state if STATE_RANK.get(existing_state, 0) > STATE_RANK.get(next_state, 0) else next_state


def _match_rule(rules: list[ClassificationRule], normalized_full_prefix: str, normalized_basename: str) -> ClassificationRule | None:
    for rule in rules:
        haystack = normalized_basename if rule.match_scope == 'basename' else normalized_full_prefix
        pattern = rule.pattern.strip().lower()
        if pattern and pattern in haystack:
            return rule
    return None


def _upsert_discovered_prefix(
    db: Session,
    *,
    scan_job_id: str,
    bucket: str,
    prefix: str,
    has_raw_child: bool,
    has_processed_child: bool,
    has_episode_grandchild: bool,
) -> None:
    record = db.query(DiscoveredPrefix).filter(
        DiscoveredPrefix.bucket == bucket,
        DiscoveredPrefix.prefix == prefix,
    ).first()
    is_list_candidate = bool((has_raw_child or has_processed_child) and has_episode_grandchild)
    if not record:
        record = DiscoveredPrefix(
            scan_job_id=scan_job_id,
            bucket=bucket,
            prefix=prefix,
            depth=_prefix_depth(prefix),
            has_raw_child=has_raw_child,
            has_processed_child=has_processed_child,
            has_episode_grandchild=has_episode_grandchild,
            is_list_candidate=is_list_candidate,
            first_seen_scan_id=scan_job_id,
            last_seen_scan_id=scan_job_id,
        )
        db.add(record)
        return

    record.scan_job_id = scan_job_id
    record.depth = _prefix_depth(prefix)
    record.has_raw_child = has_raw_child
    record.has_processed_child = has_processed_child
    record.has_episode_grandchild = has_episode_grandchild
    record.is_list_candidate = is_list_candidate
    record.last_seen_scan_id = scan_job_id


def _execute_minio_scan(
    db: Session,
    *,
    scan_job: ScanJob,
    operator: User,
    service: MinioService,
) -> ScanJob:
    normalized_bucket = scan_job.bucket.strip()
    try:
        _cleanup_stale_jobs(db, normalized_bucket)

        prefix_info: dict[str, dict[str, object]] = defaultdict(lambda: {
            'children': set(),
            'raw_episodes': set(),
            'processed_episodes': set(),
        })
        object_rows_by_prefix: dict[str, list[dict[str, object]]] = defaultdict(list)

        for item in _retry_minio(lambda: list(service.list_objects(normalized_bucket, recursive=True))):
            object_key = getattr(item, 'object_name', '').strip()
            if not object_key or object_key.endswith('/'):
                continue
            parts = [segment for segment in object_key.split('/') if segment]
            if len(parts) < 2:
                continue

            for index in range(len(parts) - 1):
                parent_prefix = _prefix_from_parts(parts, index)
                child_name = parts[index]
                prefix_info[parent_prefix]['children'].add(child_name)
                if child_name in {'raw', 'processed'} and index + 1 < len(parts) - 1 and EPISODE_PATTERN.match(parts[index + 1]):
                    episode_name = parts[index + 1]
                    prefix_info[parent_prefix][f'{child_name}_episodes'].add(episode_name)

            object_row = {
                'object_key': object_key,
                'size_bytes': int(getattr(item, 'size', 0) or 0),
                'content_hash': str(getattr(item, 'etag', '') or '').strip('"'),
                'last_modified': getattr(item, 'last_modified', None),
            }
            for index in range(len(parts) - 1):
                if parts[index] in {'raw', 'processed'} and EPISODE_PATTERN.match(parts[index + 1]):
                    episode_scope_prefix = _prefix_from_parts(parts, index + 2)
                    object_rows_by_prefix[episode_scope_prefix].append(object_row)
                    break

        current_prefixes = sorted(prefix_info.keys(), key=lambda value: (_prefix_depth(value), value))
        kept_lists: set[str] = set()
        candidates = [
            prefix
            for prefix, info in prefix_info.items()
            if info['raw_episodes'] or info['processed_episodes']
        ]
        for prefix in sorted(candidates, key=lambda value: (_prefix_depth(value), value), reverse=True):
            has_direct_episodes = bool(prefix_info[prefix]['raw_episodes'] or prefix_info[prefix]['processed_episodes'])
            has_kept_descendant = any(other != prefix and other.startswith(prefix) for other in kept_lists)
            if has_direct_episodes or not has_kept_descendant:
                kept_lists.add(_canonical_list_prefix(prefix))

        for prefix in current_prefixes:
            children = prefix_info[prefix]['children']
            _upsert_discovered_prefix(
                db,
                scan_job_id=scan_job.id,
                bucket=normalized_bucket,
                prefix=prefix,
                has_raw_child='raw' in children,
                has_processed_child='processed' in children,
                has_episode_grandchild=bool(prefix_info[prefix]['raw_episodes'] or prefix_info[prefix]['processed_episodes']),
            )

        scan_job.total_prefixes = len(current_prefixes)
        scan_job.status = 'classifying'
        scan_job.error_detail = f'prefixes={scan_job.total_prefixes} classifying'
        db.commit()
        db.refresh(scan_job)

        classification_rules = db.query(ClassificationRule).filter(ClassificationRule.is_active == True).order_by(
            ClassificationRule.priority.desc(),
            ClassificationRule.pattern.desc(),
            ClassificationRule.id.asc(),
        ).all()

        current_list_ids: set[str] = set()
        current_episode_inventory_ids: set[str] = set()
        new_episode_count = 0

        for list_prefix in sorted(kept_lists):
            list_id = _list_id(normalized_bucket, list_prefix)
            current_list_ids.add(list_id)
            raw_episode_names = set(prefix_info[list_prefix]['raw_episodes'])
            processed_episode_names = set(prefix_info[list_prefix]['processed_episodes'])
            normalized_full_prefix, normalized_basename = _normalize_classification_text(list_prefix)
            rule = _match_rule(classification_rules, normalized_full_prefix, normalized_basename)
            now = _utcnow()

            list_record = db.query(ListRecord).filter(ListRecord.id == list_id).first()
            if not list_record:
                list_record = ListRecord(
                    id=list_id,
                    bucket=normalized_bucket,
                    list_prefix=list_prefix,
                    confirmed_scan_id=scan_job.id,
                    last_active_scan_id=scan_job.id,
                    has_raw=bool(raw_episode_names),
                    has_processed=bool(processed_episode_names),
                    total_raw_episodes=len(raw_episode_names),
                    total_processed_episodes=len(processed_episode_names),
                    candidate_task_type='',
                    candidate_source='',
                    final_task_type_id=None,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(list_record)
            else:
                list_record.last_active_scan_id = scan_job.id
                list_record.has_raw = bool(raw_episode_names)
                list_record.has_processed = bool(processed_episode_names)
                list_record.total_raw_episodes = len(raw_episode_names)
                list_record.total_processed_episodes = len(processed_episode_names)
                list_record.is_active = True
                list_record.updated_at = now

            if rule:
                list_record.candidate_task_type = rule.candidate_label
                list_record.candidate_source = 'prefix_keyword'
                if rule.is_authoritative and not list_record.final_task_type_id:
                    list_record.final_task_type_id = rule.target_task_type_id
            else:
                list_record.candidate_task_type = ''
                list_record.candidate_source = ''

            task_type = _ensure_task_type(db, 'task_type:unclassified', '待分类')
            list_record.final_task_type_id = task_type.id

            batch_id = _batch_id(list_id)
            batch = db.query(Batch).filter(Batch.id == batch_id).first()
            canonical_batch_name = _batch_name(list_prefix)
            if not batch:
                batch = Batch(
                    id=batch_id,
                    list_id=list_id,
                    task_type_id=task_type.id,
                    name=canonical_batch_name,
                    imported_at=now,
                    episode_count=0,
                    sampled_episode_count=0,
                    completed_sample_count=0,
                    dispatch_mode='sampled',
                    sampling_ratio=25,
                    qc_status='new',
                    pass_rate=0.0,
                    top_reason='-',
                )
                db.add(batch)
            else:
                batch.list_id = list_id
                if batch.task_type_id == 'task_type:unclassified':
                    batch.task_type_id = task_type.id
                batch.name = canonical_batch_name

            ep_counter = 0
            total_eps = len(raw_episode_names | processed_episode_names)
            for episode_name in sorted(raw_episode_names | processed_episode_names):
                ep_counter += 1
                episode_inventory_id = _episode_inventory_id(normalized_bucket, list_prefix, episode_name)
                current_episode_inventory_ids.add(episode_inventory_id)
                raw_prefix = f'{list_prefix}raw/{episode_name}/' if episode_name in raw_episode_names else ''
                processed_prefix = f'{list_prefix}processed/{episode_name}/' if episode_name in processed_episode_names else ''
                episode_prefix = processed_prefix or raw_prefix
                episode_objects = [
                    *object_rows_by_prefix.get(raw_prefix, []),
                    *object_rows_by_prefix.get(processed_prefix, []),
                ]
                normalized_roles: list[str] = []
                manifest_hash = ''
                metadata_hash = ''
                manifest_key = ''

                inventory = db.query(EpisodeInventory).filter(EpisodeInventory.id == episode_inventory_id).first()
                previous_state = inventory.state if inventory else None
                if not inventory:
                    inventory = EpisodeInventory(
                        id=episode_inventory_id,
                        list_id=list_id,
                        episode_name=episode_name,
                        episode_prefix=episode_prefix,
                        raw_prefix=raw_prefix,
                        processed_prefix=processed_prefix,
                        state='ingestable',
                        raw_exists=bool(raw_prefix),
                        processed_exists=bool(processed_prefix),
                        manifest_hash='',
                        metadata_hash='',
                        episode_id_from_manifest='',
                        duration_sec=0,
                        frame_count=0,
                        state_changed_at=None,
                        first_seen_scan_id=scan_job.id,
                        last_seen_scan_id=scan_job.id,
                        ingested_episode_id=None,
                    )
                    db.add(inventory)
                    new_episode_count += 1
                else:
                    inventory.list_id = list_id
                    inventory.episode_prefix = episode_prefix
                    inventory.raw_prefix = raw_prefix
                    inventory.processed_prefix = processed_prefix
                    inventory.raw_exists = bool(raw_prefix)
                    inventory.processed_exists = bool(processed_prefix)
                    inventory.last_seen_scan_id = scan_job.id

                for object_row in episode_objects:
                    object_key = str(object_row['object_key'])
                    object_scope = 'processed' if processed_prefix and object_key.startswith(processed_prefix) else 'raw'
                    episode_scope_prefix = processed_prefix if object_scope == 'processed' else raw_prefix
                    relative_key = _relative_key(episode_scope_prefix, object_key)
                    object_role = _classify_object_role(object_scope, relative_key)
                    normalized_roles.append(object_role)
                    if object_role == 'manifest' and not manifest_hash:
                        manifest_key = object_key
                        manifest_hash = str(object_row['content_hash'])
                    if object_role == 'metadata' and not metadata_hash:
                        metadata_hash = str(object_row['content_hash'])

                    episode_object = db.query(EpisodeObject).filter(
                        EpisodeObject.episode_inventory_id == episode_inventory_id,
                        EpisodeObject.object_key == object_key,
                    ).first()
                    if not episode_object:
                        episode_object = EpisodeObject(
                            episode_inventory_id=episode_inventory_id,
                            object_key=object_key,
                            object_scope=object_scope,
                            object_role=object_role,
                            size_bytes=int(object_row['size_bytes']),
                            content_hash=str(object_row['content_hash']),
                            last_modified=object_row['last_modified'],
                            last_seen_scan_id=scan_job.id,
                        )
                        db.add(episode_object)
                    else:
                        episode_object.object_scope = object_scope
                        episode_object.object_role = object_role
                        episode_object.size_bytes = int(object_row['size_bytes'])
                        episode_object.content_hash = str(object_row['content_hash'])
                        episode_object.last_modified = object_row['last_modified']
                        episode_object.last_seen_scan_id = scan_job.id

                duration_sec = 0.0
                frame_count = 0
                manifest: dict | None = None
                if manifest_key:
                    try:
                        manifest = _read_json_object(service, normalized_bucket, manifest_key)
                        duration_sec, frame_count = _extract_manifest_metrics(manifest)
                    except Exception as exc:
                        logger.warning(
                            '[scan] manifest metrics unavailable bucket=%s key=%s error=%s: %s',
                            normalized_bucket,
                            manifest_key,
                            type(exc).__name__,
                            exc,
                        )

                inventory.duration_sec = duration_sec
                inventory.frame_count = frame_count

                inventory.manifest_hash = manifest_hash
                inventory.metadata_hash = metadata_hash
                inventory.episode_id_from_manifest = episode_name
                derived_state = _derive_state(
                    raw_exists=bool(raw_prefix),
                    processed_exists=bool(processed_prefix),
                    roles=normalized_roles,
                    manifest_data=manifest,
                )
                next_state = _apply_state_transition(previous_state, derived_state)
                if previous_state != next_state:
                    inventory.state_changed_at = now
                inventory.state = next_state

                episode_id = _episode_id(batch_id, episode_name)
                episode = db.query(Episode).filter(Episode.id == episode_id).first()
                if not episode:
                    episode = Episode(
                        id=episode_id,
                        batch_id=batch.id,
                        task_name=task_type.name,
                        duration_sec=duration_sec,
                        frame_count=frame_count,
                        qc_status='new',
                        qc_result='pending',
                        reviewer='-',
                        reason_code='-',
                        updated_at=now,
                        in_candidate_pool=1,
                        sampled_for_qc=0,
                    )
                    db.add(episode)
                else:
                    episode.batch_id = batch.id
                    episode.task_name = task_type.name
                    episode.updated_at = now
                    episode.duration_sec = duration_sec
                    episode.frame_count = frame_count
                inventory.ingested_episode_id = episode.id

                if ep_counter % 50 == 0 and total_eps > 0:
                    scan_job.error_detail = f'classifying {ep_counter}/{total_eps}'
                    db.commit()

            if list_prefix != _canonical_list_prefix(list_prefix):
                legacy_batch_id = _batch_id(_list_id(normalized_bucket, list_prefix))
                legacy_episode_id = _episode_id(legacy_batch_id, 'episode_000000')
                _cleanup_replaced_batch(
                    db,
                    canonical_batch_id=batch_id,
                    canonical_batch_name=canonical_batch_name,
                    legacy_batch_id=legacy_batch_id,
                    legacy_episode_id=legacy_episode_id,
                )

            batch.episode_count = len(raw_episode_names | processed_episode_names)
            enqueue_batch_asset_recompute(db, batch.id, reason='scan_sync')
            scan_job.confirmed_lists = len(current_list_ids)
            scan_job.total_episodes = len(current_episode_inventory_ids)
            scan_job.new_episodes = new_episode_count
            scan_job.error_detail = f'lists={scan_job.confirmed_lists} episodes={scan_job.total_episodes} new={scan_job.new_episodes}'
            db.commit()

        for list_record in db.query(ListRecord).filter(ListRecord.bucket == normalized_bucket).all():
            if list_record.id not in current_list_ids:
                if list_record.is_active:
                    enqueue_list_scope_recompute(db, list_record.id, reason='list_scope_changed')
                list_record.is_active = False
                list_record.updated_at = _utcnow()

        scan_job.status = 'done'
        scan_job.confirmed_lists = len(current_list_ids)
        scan_job.total_episodes = len(current_episode_inventory_ids)
        scan_job.new_episodes = new_episode_count
        scan_job.finished_at = _utcnow()
        db.add(AuditEvent(
            id=f'audit_{scan_job.id}',
            operator=operator.name,
            action='MinIO扫描',
            target=normalized_bucket,
            detail=f'lists={scan_job.confirmed_lists} episodes={scan_job.total_episodes} new={scan_job.new_episodes}',
            time=_utcnow(),
        ))
        db.commit()
        db.refresh(scan_job)
        return scan_job
    except S3Error as exc:
        scan_job.status = 'failed'
        scan_job.error_detail = str(exc)
        scan_job.finished_at = _utcnow()
        db.commit()
        db.refresh(scan_job)
        raise ValueError(f'MinIO 扫描失败: {exc}') from exc
    except Exception as exc:
        scan_job.status = 'failed'
        scan_job.error_detail = str(exc)
        scan_job.finished_at = _utcnow()
        db.commit()
        db.refresh(scan_job)
        raise


def run_minio_scan(
    db: Session,
    *,
    bucket: str,
    operator: User,
    scope: str = 'full',
    minio_service: MinioService | None = None,
) -> ScanJob:
    require_roles(operator, 'admin', 'qc_manager')
    normalized_bucket = bucket.strip()
    if not normalized_bucket:
        raise ValueError('bucket 不能为空')

    service = minio_service or get_minio_service()
    scan_job = ScanJob(
        id=_scan_job_id(normalized_bucket),
        bucket=normalized_bucket,
        scope=scope,
        status='scanning',
        total_prefixes=0,
        confirmed_lists=0,
        total_episodes=0,
        new_episodes=0,
        triggered_by=operator.id,
        error_detail='',
        started_at=_utcnow(),
        finished_at=None,
    )
    db.add(scan_job)
    db.flush()
    return _execute_minio_scan(db, scan_job=scan_job, operator=operator, service=service)


def resume_minio_scan(
    db: Session,
    *,
    scan_job_id: str,
    operator: User,
    minio_service: MinioService | None = None,
) -> ScanJob:
    require_roles(operator, 'admin', 'qc_manager')
    scan_job = db.query(ScanJob).filter(ScanJob.id == scan_job_id).first()
    if not scan_job:
        raise ValueError('scan job 不存在')
    scan_job.status = 'scanning'
    scan_job.error_detail = ''
    scan_job.started_at = _utcnow()
    scan_job.finished_at = None
    db.commit()
    db.refresh(scan_job)
    service = minio_service or get_minio_service()
    return _execute_minio_scan(db, scan_job=scan_job, operator=operator, service=service)
