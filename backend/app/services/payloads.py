from __future__ import annotations

import io
import json
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models import AuditEvent, Batch, BugReport, Episode, EpisodeInventory, EpisodeObject, ListRecord, QcReviewRevision, QcTask, ScanJob, TaskType, User
from app.services.data_assets import active_batch_query as _data_assets_active_batch_query
from app.services.data_assets import active_episode_query as _data_assets_active_episode_query
from app.services.minio_client import get_minio_service

UNCLASSIFIED_TASK_TYPE_ID = 'task_type:unclassified'
RECENT_SCAN_JOB_LIMIT = 20

settings = get_settings()
APP_ZONE = ZoneInfo(settings.app_timezone)


def format_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(APP_ZONE).strftime('%Y-%m-%d %H:%M')


def format_optional_time(value: datetime | None) -> str | None:
    return format_time(value) if value else None


def serialize_user(user: User) -> dict:
    return {
        'id': user.id,
        'name': user.name,
        'role': user.role,
        'avatar': user.avatar,
    }


def serialize_account(user: User) -> dict:
    return {
        'id': user.id,
        'username': user.username,
        'name': user.name,
        'role': user.role,
        'avatar': user.avatar,
        'isActive': bool(user.is_active),
        'passwordChangedAt': format_optional_time(user.password_changed_at),
    }


def serialize_task_type(task_type: TaskType) -> dict:
    return {
        'id': task_type.id,
        'name': task_type.name,
        'description': task_type.description,
        'armMode': task_type.arm_mode,
        'isActive': bool(task_type.is_active),
        'totalBatches': task_type.total_batches,
        'totalEpisodes': task_type.total_episodes,
    }


def _lookup_inventory_for_episode(db: Session, episode_id: str):
    return db.query(EpisodeInventory, ListRecord.bucket).join(
        ListRecord, EpisodeInventory.list_id == ListRecord.id
    ).filter(
        (EpisodeInventory.ingested_episode_id == episode_id)
        | (EpisodeInventory.episode_id_from_manifest == episode_id)
        | (EpisodeInventory.episode_name == episode_id)
    ).order_by(EpisodeInventory.last_seen_scan_id.desc()).first()


def _batch_storage_location(db: Session, batch: Batch) -> tuple[str, str]:
    for episode in batch.episodes:
        inventory = _lookup_inventory_for_episode(db, episode.id)
        if inventory:
            episode_inventory, bucket = inventory
            return bucket, episode_inventory.processed_prefix or episode_inventory.raw_prefix or episode_inventory.episode_prefix
    return '', ''


def _prefetch_batch_storage_locations(db: Session, batch_ids: Iterable[str]) -> dict[str, tuple[str, str]]:
    batch_ids = [item for item in batch_ids if item]
    if not batch_ids:
        return {}

    rows = db.query(
        Batch.id,
        ListRecord.bucket,
        ListRecord.list_prefix,
        EpisodeInventory.processed_prefix,
        EpisodeInventory.raw_prefix,
        EpisodeInventory.episode_prefix,
    ).join(
        ListRecord,
        Batch.list_id == ListRecord.id,
    ).outerjoin(
        EpisodeInventory,
        EpisodeInventory.list_id == ListRecord.id,
    ).filter(
        Batch.id.in_(batch_ids),
        Batch.is_active == True,
        ListRecord.is_active == True,
    ).order_by(
        Batch.id.asc(),
        EpisodeInventory.last_seen_scan_id.desc(),
        EpisodeInventory.id.asc(),
    ).all()

    locations: dict[str, tuple[str, str]] = {}
    for row in rows:
        if row.id in locations:
            continue
        prefix = row.processed_prefix or row.raw_prefix or row.episode_prefix or row.list_prefix or ''
        locations[row.id] = (row.bucket or '', prefix)

    return locations


def _active_batch_query(db: Session):
    return _data_assets_active_batch_query(db)


def _active_episode_query(db: Session):
    return _data_assets_active_episode_query(db)


def _batch_query(db: Session):
    return _active_batch_query(db)


def _task_type_batch_query(db: Session, task_type_id: str):
    return _batch_query(db).filter(Batch.task_type_id == task_type_id)


def task_type_active_counts(db: Session, task_type_id: str) -> tuple[int, int]:
    """业务口径的任务类型批次/集数：仅统计在 lists 控制面有 active 记录的批次，
    与 database/总库列表一致，排除无 ListRecord 的历史残留批次（如 raw_data）。"""
    batch_count = _task_type_batch_query(db, task_type_id).count()
    episode_count = _active_episode_query(db).filter(Batch.task_type_id == task_type_id).count()
    return batch_count, episode_count


def serialize_batch(db: Session, batch: Batch, storage_locations: dict[str, tuple[str, str]] | None = None) -> dict:
    coverage = round((batch.sampled_episode_count / batch.episode_count) * 100) if batch.episode_count else 0
    completion = round((batch.completed_sample_count / batch.sampled_episode_count) * 100) if batch.sampled_episode_count else 0
    if storage_locations and batch.id in storage_locations:
        bucket, storage_prefix = storage_locations[batch.id]
    else:
        bucket, storage_prefix = _batch_storage_location(db, batch)
    return {
        'id': batch.id,
        'taskTypeId': batch.task_type_id,
        'name': batch.name,
        'importedAt': format_time(batch.imported_at),
        'episodeCount': batch.episode_count,
        'sampledEpisodeCount': batch.sampled_episode_count,
        'completedSampleCount': batch.completed_sample_count,
        'sampleCoverageRate': coverage,
        'sampleReviewCompletionRate': completion,
        'dispatchMode': batch.dispatch_mode,
        'samplingRatio': batch.sampling_ratio,
        'qcStatus': batch.qc_status,
        'passRate': batch.pass_rate,
        'topReason': batch.top_reason,
        'bucket': bucket,
        'storagePrefix': storage_prefix,
    }


def _serialize_batches(db: Session, batches: list[Batch]) -> list[dict]:
    storage_locations = _prefetch_batch_storage_locations(db, [item.id for item in batches])
    return [serialize_batch(db, item, storage_locations) for item in batches]


def _recent_ingest_jobs_payload(db: Session, limit: int = RECENT_SCAN_JOB_LIMIT) -> list[dict]:
    jobs = db.query(ScanJob).order_by(ScanJob.started_at.desc()).limit(limit).all()
    return [serialize_ingest_job(item) for item in jobs]


def sync_batch_metrics(db: Session, batch: Batch) -> None:
    sampled_count = db.query(func.count(Episode.id)).filter(Episode.batch_id == batch.id, Episode.sampled_for_qc == 1).scalar() or 0
    completed_count = db.query(func.count(Episode.id)).filter(Episode.batch_id == batch.id, Episode.sampled_for_qc == 1, Episode.qc_status == 'done').scalar() or 0
    passed_count = db.query(func.count(Episode.id)).filter(Episode.batch_id == batch.id, Episode.sampled_for_qc == 1, Episode.qc_result == 'pass').scalar() or 0
    manual_pass_count = db.query(func.count(Episode.id)).filter(Episode.batch_id == batch.id, Episode.sampled_for_qc == 1, Episode.manual_qc_status == 'MANUAL_PASS').scalar() or 0
    manual_fail_count = db.query(func.count(Episode.id)).filter(Episode.batch_id == batch.id, Episode.sampled_for_qc == 1, Episode.manual_qc_status == 'MANUAL_FAIL').scalar() or 0
    top_reason = db.query(Episode.reason_code, func.count(Episode.id).label('count')).filter(
        Episode.batch_id == batch.id,
        Episode.sampled_for_qc == 1,
        Episode.reason_code != '-',
    ).group_by(Episode.reason_code).order_by(func.count(Episode.id).desc(), Episode.reason_code.asc()).first()

    batch.sampled_episode_count = sampled_count
    batch.completed_sample_count = completed_count
    batch.manual_pass_count = manual_pass_count
    batch.manual_fail_count = manual_fail_count
    batch.pass_rate = round((passed_count / completed_count) * 100, 1) if completed_count else 0.0
    batch.top_reason = top_reason[0] if top_reason else '-'
    if completed_count and completed_count >= sampled_count and sampled_count > 0:
        batch.qc_status = 'done'
    elif sampled_count > 0:
        batch.qc_status = 'in_review'
    else:
        batch.qc_status = 'new'


def serialize_episode(episode: Episode) -> dict:
    return {
        'id': episode.id,
        'batchId': episode.batch_id,
        'batchName': episode.batch.name,
        'taskName': episode.task_name,
        'durationSec': episode.duration_sec,
        'frameCount': episode.frame_count,
        'fps': None,
        'qcStatus': episode.qc_status,
        'qcResult': episode.qc_result,
        'reviewer': episode.reviewer,
        'reasonCode': episode.reason_code,
        'updatedAt': format_time(episode.updated_at),
        'finalDatasetStatus': episode.final_dataset_status,
        'finalDecisionSource': episode.final_decision_source,
    }


def review_lock_payload(task: QcTask, current_user: User | None = None) -> dict:
    now = datetime.utcnow()
    is_locked = bool(task.lock_owner_user_id and task.lock_expires_at and task.lock_expires_at > now)
    is_mine = bool(current_user and task.lock_owner_user_id == current_user.id and is_locked)
    owner_user_id = task.lock_owner_user_id if is_locked else ''
    owner_name = task.lock_owner_name if is_locked else ''
    acquired_at = task.lock_acquired_at if is_locked else None
    expires_at = task.lock_expires_at if is_locked else None
    return {
        'isLocked': is_locked,
        'isMine': is_mine,
        'ownerUserId': owner_user_id,
        'ownerName': owner_name,
        'acquiredAt': format_optional_time(acquired_at),
        'expiresAt': format_optional_time(expires_at),
        'version': task.version,
    }


def serialize_task(task: QcTask, current_user: User | None = None) -> dict:
    # Fix stale in_review state from expired locks
    now = datetime.utcnow()
    if task.status == 'in_review':
        has_active_lock = task.lock_owner_user_id and task.lock_expires_at and task.lock_expires_at > now
        if not has_active_lock:
            task.status = 'assigned' if task.assignee != '未派发' else 'new'
            task.lock_owner_user_id = ''
            task.lock_owner_name = ''
            task.lock_acquired_at = None
            task.lock_expires_at = None
    return {
        'id': task.id,
        'episodeId': task.episode_id,
        'batchId': task.batch_id,
        'batchName': task.batch_name,
        'taskName': task.task_name,
        'assignee': task.assignee,
        'status': task.status,
        'priority': task.priority,
        'dispatchMode': task.dispatch_mode,
        'samplingRatio': task.sampling_ratio,
        'dispatchGeneration': task.dispatch_generation,
        'isActive': bool(task.is_active),
        'assignmentMode': task.assignment_mode,
        'createdAt': format_time(task.created_at),
        'reviewLock': review_lock_payload(task, current_user),
    }


def _manual_qc_permissions(task: QcTask | None, current_user: User | None = None) -> tuple[str, bool, bool]:
    if not task or not current_user:
        return 'history', False, False

    task_payload = serialize_task(task, current_user)
    review_lock = task_payload['reviewLock']
    if current_user.role == 'admin':
        can_claim = bool(task.is_active and task.status in ('new', 'assigned', 'done') and (not review_lock['isLocked'] or review_lock['isMine']))
        can_submit = bool(review_lock['isMine'] and task.status == 'in_review')
        return 'active', can_claim, can_submit

    if current_user.role == 'reviewer':
        can_claim = bool(task.is_active and task.status == 'assigned' and task.assignee == current_user.name and not review_lock['isLocked'])
        can_submit = bool(review_lock['isMine'] and task.status == 'in_review')
        if task.status == 'done':
            return 'history', False, False
        return 'active', can_claim, can_submit

    can_submit = bool(review_lock['isMine'] and task.status == 'in_review')
    return ('active' if task.status != 'done' else 'history'), False, can_submit


def serialize_bug_report(report: BugReport) -> dict:
    import json as _json
    filenames: list[str] = []
    if report.image_filename:
        try:
            parsed = _json.loads(report.image_filename)
            if isinstance(parsed, list):
                filenames = parsed
            else:
                filenames = [str(parsed)]
        except (ValueError, TypeError):
            filenames = [report.image_filename]
    return {
        'id': report.id,
        'description': report.description,
        'status': report.status,
        'imageUrls': [f'/api/bug-reports/{report.id}/image/{idx}' for idx in range(len(filenames))],
        'reporterUserId': report.reporter_user_id,
        'reporterName': report.reporter_name,
        'createdAt': format_time(report.created_at),
        'updatedAt': format_time(report.updated_at),
    }


def serialize_revision(revision: QcReviewRevision) -> dict:
    episode = revision.episode
    batch = episode.batch
    return {
        'episodeId': revision.episode_id,
        'batchId': episode.batch_id,
        'batchName': batch.name,
        'revisionNo': revision.revision_no,
        'result': revision.result,
        'primaryReason': revision.primary_reason,
        'operator': revision.operator,
        'time': format_time(revision.time),
        'note': revision.note,
    }


def serialize_audit(audit: AuditEvent) -> dict:
    return {
        'id': audit.id,
        'operator': audit.operator,
        'action': audit.action,
        'target': audit.target,
        'time': format_time(audit.time),
        'detail': audit.detail,
        'eventType': audit.event_type,
        'severity': audit.severity,
        'operatorId': audit.operator_id,
        'ipAddress': audit.ip_address,
        'userAgent': audit.user_agent,
        'durationMs': audit.duration_ms,
    }


def serialize_ingest_job(job: ScanJob) -> dict:
    if job.status == 'done':
        progress = 100
    elif job.status == 'classifying':
        progress = 70
    elif job.status == 'scanning':
        progress = 15
    else:
        progress = 0
    return {
        'id': job.id,
        'bucket': job.bucket,
        'scope': job.scope,
        'status': job.status,
        'progress': progress,
        'confirmedLists': job.confirmed_lists,
        'totalEpisodes': job.total_episodes,
        'newEpisodes': job.new_episodes,
        'detail': job.error_detail or f'lists={job.confirmed_lists} episodes={job.total_episodes} new={job.new_episodes}',
        'startedAt': format_time(job.started_at),
        'finishedAt': format_time(job.finished_at) if job.finished_at else None,
    }


def _read_minio_json(bucket: str, object_key: str) -> dict:
    response = get_minio_service().get_object(bucket, object_key)
    try:
        return json.loads(response.read().decode('utf-8'))
    finally:
        response.close()
        response.release_conn()


def _build_preview_url(bucket: str, object_key: str, *, expires: timedelta) -> str:
    return get_minio_service().presigned_get_object(bucket, object_key, expires=expires)


def _media_preview_expiry(expires: timedelta) -> str:
    return (datetime.utcnow() + expires).replace(microsecond=0).isoformat() + 'Z'


def _camera_slot_map_from_manifest(manifest: dict) -> dict[str, dict[str, object]]:
    """Return {video_basename: {slot, label}} from manifest files.cameras."""
    cameras = manifest.get('files', {}).get('cameras', {}) if isinstance(manifest.get('files'), dict) else {}
    slot_labels = {
        'cam_top': ('top', 'Top Camera'),
        'cam_left_wrist': ('left', 'Left Wrist'),
        'cam_right_wrist': ('right', 'Right Wrist'),
    }
    mapping: dict[str, dict[str, object]] = {}
    for cam_key, info in cameras.items():
        slot, label = slot_labels.get(cam_key, ('unknown', cam_key.replace('_', ' ').title()))
        video_path = info.get('video', '') if isinstance(info, dict) else ''
        basename = video_path.rsplit('/', 1)[-1] if video_path else ''
        if basename:
            mapping[basename] = {'slot': slot, 'label': label}
    return mapping


def _media_slot_and_label(object_key: str, cam_slot_map: dict[str, dict[str, object]] | None = None) -> tuple[str, str]:
    basename = object_key.rsplit('/', 1)[-1]
    if cam_slot_map and basename in cam_slot_map:
        info = cam_slot_map[basename]
        return str(info['slot']), str(info['label'])
    return 'top', 'Top Camera'


def _media_variant_from_key(object_key: str, cam_slot_map: dict[str, dict[str, object]] | None = None) -> str:
    basename = object_key.rsplit('/', 1)[-1]
    normalized = basename.lower()
    if 'depth' in normalized and 'colormap' in normalized:
        return 'depth_colormap'
    if cam_slot_map and basename in cam_slot_map:
        return 'rgb'
    return 'rgb'


def _manual_qc_media(db: Session, episode_id: str, current_user: User | None) -> list[dict]:
    inventory_row = _lookup_inventory_for_episode(db, episode_id)
    if not inventory_row:
        return []

    inventory, bucket = inventory_row
    task = db.query(QcTask).filter(QcTask.episode_id == episode_id, QcTask.is_active == 1).order_by(QcTask.dispatch_generation.desc(), QcTask.created_at.desc()).first()
    review_lock = review_lock_payload(task, current_user) if task else None
    refreshable = bool(review_lock and review_lock['isMine'])
    preview_ttl = timedelta(minutes=5)

    # Build camera slot map from manifest (manifest-key based lookup)
    cam_slot_map: dict[str, dict[str, object]] = {}
    manifest_key = next((row.object_key for row in db.query(EpisodeObject).filter(
        EpisodeObject.episode_inventory_id == inventory.id,
        EpisodeObject.object_role == 'manifest',
    ).limit(1)), None)
    if manifest_key:
        try:
            manifest = _read_minio_json(bucket, manifest_key)
            cam_slot_map = _camera_slot_map_from_manifest(manifest)
        except Exception:
            pass

    media_items = []
    object_rows = db.query(EpisodeObject).filter(
        EpisodeObject.episode_inventory_id == inventory.id,
        EpisodeObject.object_scope == 'processed',
        EpisodeObject.object_key.like('%.mp4'),
    ).order_by(EpisodeObject.object_key.asc()).all()

    # Dynamic sort order from camera enumeration
    cam_order = [info['slot'] for info in cam_slot_map.values()]
    if not cam_order:
        cam_order = ['top', 'left', 'right']
    slot_sort = {slot: (i + 1) * 10 for i, slot in enumerate(cam_order)}

    for item in object_rows:
        slot, label = _media_slot_and_label(item.object_key, cam_slot_map)
        variant = _media_variant_from_key(item.object_key, cam_slot_map)
        media_items.append({
            'objectId': str(item.id),
            'role': item.object_role,
            'label': label,
            'variant': variant,
            'slot': slot,
            'mimeType': 'video/mp4',
            'previewUrl': _build_preview_url(bucket, item.object_key, expires=preview_ttl),
            'previewExpiresAt': _media_preview_expiry(preview_ttl),
            'refreshable': refreshable,
            'downloadable': True,
            'sortOrder': slot_sort.get(slot, 100) + (1 if variant == 'depth_colormap' else 0),
        })

    return sorted(media_items, key=lambda item: (item['sortOrder'], item['label'], item['variant']))


def _read_minio_npz(bucket: str, object_key: str):
    response = get_minio_service().get_object(bucket, object_key)
    try:
        payload = response.read()
    finally:
        response.close()
        response.release_conn()
    return np.load(io.BytesIO(payload), allow_pickle=False)


def _read_minio_npy(bucket: str, object_key: str) -> npt.NDArray[np.float64] | None:
    response = get_minio_service().get_object(bucket, object_key)
    try:
        payload = response.read()
    finally:
        response.close()
        response.release_conn()
    arr = np.load(io.BytesIO(payload), allow_pickle=False)
    return np.asarray(arr, dtype=np.float64).ravel() if arr.size else None


def _build_real_manual_qc_context(db: Session, episode_id: str) -> dict | None:
    inventory_row = _lookup_inventory_for_episode(db, episode_id)
    if not inventory_row:
        return None

    episode = db.query(Episode).options(joinedload(Episode.batch).joinedload(Batch.task_type)).filter(Episode.id == episode_id).first()
    if not episode or not episode.batch or not episode.batch.task_type:
        return None
    arm_mode = episode.batch.task_type.arm_mode or 'both_arms'

    inventory, bucket = inventory_row
    object_rows = db.query(EpisodeObject).filter(
        EpisodeObject.episode_inventory_id == inventory.id,
        EpisodeObject.object_scope == 'processed',
    ).all()
    object_map = {item.object_role: item.object_key for item in object_rows}
    manifest_key = object_map.get('manifest')
    metadata_key = object_map.get('metadata')
    telemetry_key = object_map.get('telemetry_npz')
    if not manifest_key or not metadata_key or not telemetry_key:
        return None

    manifest = _read_minio_json(bucket, manifest_key)
    metadata = _read_minio_json(bucket, metadata_key)

    # Use manifest to find depth camera timestamp file (no substring guessing)
    depth_ts_key: str | None = None
    cameras = manifest.get('files', {}).get('cameras', {})
    top_cam = cameras.get('cam_top', {})
    if isinstance(top_cam, dict):
        depth_ts_path = top_cam.get('timestamps', '')
        # Find matching EpisodeObject
        for item in object_rows:
            if item.object_key == depth_ts_path:
                depth_ts_key = item.object_key
                break
    # Fallback: iterate object_rows for any depth timestamp
    if not depth_ts_key:
        for item in object_rows:
            if item.object_role == 'timestamp_npy' and 'depth' in item.object_key.lower():
                depth_ts_key = item.object_key
                break
    depth_timestamps: npt.NDArray[np.float64] | None = None
    if depth_ts_key:
        depth_timestamps = _read_minio_npy(bucket, depth_ts_key)

    # Extract DOF config from metadata
    dof_config = None
    try:
        dev = (metadata.get('device') or metadata)
        arm_joints = dev.get('arm', {}).get('joints', {})
        hand_joints = dev.get('hand', {}).get('joints', {})
        dof_config = {
            'arm_left_dof': int(arm_joints.get('left_dof', 7)),
            'arm_right_dof': int(arm_joints.get('right_dof', 7)),
            'hand_left_dof': int(hand_joints.get('left_dof', 6)),
            'hand_right_dof': int(hand_joints.get('right_dof', 6)),
        }
    except Exception:
        pass

    with _read_minio_npz(bucket, telemetry_key) as telemetry:
        telemetry_dict = {key: telemetry[key] for key in telemetry.files}
        from app.services.l3_v2 import L3V2Engine
        from app.models.l3_v2_config import L3V2Config
        l3_params = L3V2Config.get_params(db)
        declared_fps = float(manifest.get('fps', 0.0))
        manifest_frame_count = int(manifest.get('frame_count', 0))
        l3_v2 = L3V2Engine(
            telemetry_dict,
            l3_params,
            depth_timestamps=depth_timestamps,
            dof_config=dof_config,
            arm_mode=arm_mode,
            declared_fps=declared_fps,
            manifest_frame_count=manifest_frame_count,
        ).compute()

    return {
        'durationSec': float(manifest.get('duration', 0.0)),
        'frameCount': int(manifest.get('frame_count', 0)),
        'fps': float(manifest.get('fps', 0.0)),
        'l3V2': l3_v2,
        'syncDescription': metadata.get('alignment', {}).get('method', ''),
    }


def task_type_detail_payload(db: Session, task_type: TaskType) -> dict:
    batches = _task_type_batch_query(db, task_type.id).options(joinedload(Batch.episodes)).order_by(Batch.imported_at.desc()).all()
    return {
        'taskType': serialize_task_type(task_type),
        'batches': _serialize_batches(db, batches),
    }


def unclassified_batch_payload(db: Session) -> list[dict]:
    batches = _task_type_batch_query(db, UNCLASSIFIED_TASK_TYPE_ID).options(joinedload(Batch.episodes)).order_by(Batch.imported_at.desc()).all()
    return _serialize_batches(db, batches)


def dashboard_payload(db: Session, current_user: User) -> dict:
    batches = _active_batch_query(db).options(joinedload(Batch.episodes)).order_by(Batch.imported_at.desc()).all()
    active_batch_ids = {item.id for item in batches}
    counts_by_batch = _task_counts_by_batch(db, active_batch_ids)
    superseded_by_batch = _superseded_task_counts_by_batch(db, active_batch_ids)
    return {
        'currentUser': serialize_user(current_user),
        'taskTypes': [serialize_task_type(item) for item in db.query(TaskType).filter(TaskType.is_active == True).order_by(TaskType.id).all()],
        'batches': _serialize_batches(db, batches),
        'qcTasks': [
            serialize_task(item, current_user)
            for item in db.query(QcTask)
            .filter(QcTask.batch_id.in_(active_batch_ids), QcTask.is_active == 1)
            .order_by(QcTask.created_at.desc())
            .all()
        ],
        'dispatchPreviews': [dispatch_preview_payload(item, counts_by_batch.get(item.id), superseded_by_batch.get(item.id, 0)) for item in batches],
        'reasonStats': reason_stats_payload_from_db(db),
        'reviewerWorkloads': reviewer_workload_payload(db),
        'reviewerAccounts': reviewer_account_payload(db),
        'ingestJobs': _recent_ingest_jobs_payload(db),
    }


def database_payload(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 100,
    keyword: str = '',
    batch_id: str = '',
    qc_status: str = '',
    qc_result: str = '',
) -> dict:
    page = max(page, 1)
    page_size = max(1, min(page_size, 200))
    normalized_keyword = keyword.strip().lower()

    episode_query = _active_episode_query(db)
    if batch_id:
        episode_query = episode_query.filter(Episode.batch_id == batch_id)
    if qc_status:
        episode_query = episode_query.filter(Episode.qc_status == qc_status)
    if qc_result:
        episode_query = episode_query.filter(Episode.final_dataset_status == qc_result)
    if normalized_keyword:
        like_term = f'%{normalized_keyword}%'
        episode_query = episode_query.filter(
            func.lower(Episode.id).like(like_term)
            | func.lower(Episode.reason_code).like(like_term)
            | func.lower(Episode.reviewer).like(like_term)
            | func.lower(Episode.task_name).like(like_term)
            | func.lower(Batch.name).like(like_term)
        )

    total_episodes = episode_query.order_by(None).count()
    episodes = episode_query.order_by(Episode.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    batches = _active_batch_query(db).order_by(Batch.imported_at.desc()).all()
    return {
        'episodes': [serialize_episode(item) for item in episodes],
        'batches': _serialize_batches(db, batches),
        'taskTypes': [serialize_task_type(item) for item in db.query(TaskType).filter(TaskType.is_active == True).order_by(TaskType.id).all()],
        'reasonStats': reason_stats_payload_from_db(db),
        'ingestJobs': _recent_ingest_jobs_payload(db),
        'totalEpisodes': total_episodes,
        'page': page,
        'pageSize': page_size,
    }


def reviewer_workload_payload(db: Session) -> list[dict]:
    rows = db.query(
        Episode.reviewer.label('name'),
        func.sum(case((Episode.qc_status.in_(['assigned', 'in_review']), 1), else_=0)).label('assigned'),
        func.sum(case((Episode.qc_status == 'done', 1), else_=0)).label('done'),
        func.sum(case((Episode.qc_result == 'pass', 1), else_=0)).label('passed'),
    ).filter(Episode.reviewer != '-').group_by(Episode.reviewer).order_by(Episode.reviewer.asc()).all()
    workloads = []
    for row in rows:
        done = row.done or 0
        assigned = row.assigned or 0
        passed = row.passed or 0
        avg_minutes = round(3.5 + done * 0.2 + assigned * 0.1, 1)
        workloads.append({
            'name': row.name,
            'assigned': assigned,
            'done': done,
            'passRate': round((passed / done) * 100, 1) if done else 0.0,
            'avgMinutes': avg_minutes,
        })
    return workloads


def reason_stats_payload() -> list[dict]:
    return [
        # L2 视觉类
        {'reason': 'blur', 'category': 'L2 视觉'},
        {'reason': 'exposure_over', 'category': 'L2 视觉'},
        {'reason': 'occlusion_hand', 'category': 'L2 视觉'},
        {'reason': 'occlusion_object', 'category': 'L2 视觉'},
        {'reason': 'object_not_visible', 'category': 'L2 视觉'},
        {'reason': 'depth_invalid', 'category': 'L2 视觉'},
        # 动作示范质量
        {'reason': 'trajectory_unsmooth', 'category': '动作示范质量'},
        {'reason': 'action_discontinuity', 'category': '动作示范质量'},
        {'reason': 'oscillation', 'category': '动作示范质量'},
        {'reason': 'chatter', 'category': '动作示范质量'},
        # 可学习性
        {'reason': 'low_effective_action', 'category': '可学习性'},
        {'reason': 'low_information_density', 'category': '可学习性'},
        {'reason': 'prolonged_idle', 'category': '可学习性'},
        # 数据完整性
        {'reason': 'sync_bad', 'category': '数据完整性'},
        {'reason': 'timestamp_irregular', 'category': '数据完整性'},
        # 执行诊断
        {'reason': 'tracking_error', 'category': '执行诊断'},
        # L4 任务类
        {'reason': 'task_incomplete', 'category': 'L4 任务'},
        {'reason': 'wrong_final_state', 'category': 'L4 任务'},
        {'reason': 'grasp_failed', 'category': 'L4 任务'},
        {'reason': 'placement_failed', 'category': 'L4 任务'},
        # 系统类
        {'reason': 'conversion_issue', 'category': '系统'},
        {'reason': 'metadata_missing', 'category': '系统'},
        {'reason': 'modality_missing', 'category': '系统'},
        {'reason': 'file_corrupted', 'category': '系统'},
        # 旧版兼容（历史数据可能有这些值）
        {'reason': 'motion_abnormal', 'category': '动作示范质量'},
        {'reason': 'stall', 'category': '可学习性'},
        {'reason': 'joint_limit_risk', 'category': '执行诊断'},
    ]


def reason_stats_payload_from_db(db: Session) -> list[dict]:
    reason_counts = db.query(
        Episode.reason_code,
        func.count(Episode.id).label('count'),
    ).filter(Episode.reason_code != '-').group_by(Episode.reason_code).order_by(func.count(Episode.id).desc(), Episode.reason_code.asc()).all()
    total = sum(item.count for item in reason_counts)
    category_map = {item['reason']: item['category'] for item in reason_stats_payload()}
    return [
        {
            'reason': item.reason_code,
            'count': item.count,
            'ratio': round(item.count * 100 / total) if total else 0,
            'category': category_map.get(item.reason_code, 'Other'),
        }
        for item in reason_counts
    ]


def history_payload(db: Session, revision_page: int = 1, revision_page_size: int = 20, audit_page: int = 1, audit_page_size: int = 50) -> dict:
    revision_query = db.query(QcReviewRevision).join(Episode, QcReviewRevision.episode_id == Episode.id).join(Batch, Episode.batch_id == Batch.id).filter(Batch.is_active == True).order_by(QcReviewRevision.time.desc(), QcReviewRevision.revision_no.desc())
    revision_total = revision_query.count()
    revisions = revision_query.offset((revision_page - 1) * revision_page_size).limit(revision_page_size).all()

    audit_query = db.query(AuditEvent).order_by(AuditEvent.time.desc())
    audit_total = audit_query.count()
    audits = audit_query.offset((audit_page - 1) * audit_page_size).limit(audit_page_size).all()

    episodes = _active_episode_query(db).options(joinedload(Episode.batch)).order_by(Episode.updated_at.desc()).all()
    # batch.episode_count / sampled_episode_count 等已冗余在 Batch 表中，无需 joinedload episodes
    batches = _batch_query(db).order_by(Batch.imported_at.desc()).all()
    return {
        'auditRecords': [serialize_audit(item) for item in audits],
        'auditTotal': audit_total,
        'qcRevisions': [serialize_revision(item) for item in revisions],
        'revisionTotal': revision_total,
        'episodes': [serialize_episode(item) for item in episodes],
        'batches': _serialize_batches(db, batches),
    }


def _latest_activity_time(batch: Batch) -> datetime | None:
    candidates = [batch.imported_at]
    candidates.extend(episode.updated_at for episode in batch.episodes if episode.updated_at)
    candidates.extend(revision.time for episode in batch.episodes for revision in episode.revisions if revision.time)
    return max(candidates) if candidates else None


def build_history_report_payload(db: Session, selected_batch_id: str = 'all') -> dict:
    batches = _batch_query(db).order_by(Batch.imported_at.desc()).all()

    scoped_batches = batches if selected_batch_id == 'all' else [item for item in batches if item.id == selected_batch_id]
    scoped_batch_ids = {item.id for item in scoped_batches}

    if not scoped_batch_ids:
        return {
            'generatedAt': format_time(datetime.utcnow()),
            'selectedBatchId': selected_batch_id,
            'summary': {'batchCount': 0, 'episodeCount': 0, 'sampledEpisodeCount': 0, 'completedSampleCount': 0, 'failEpisodeCount': 0, 'passEpisodeCount': 0, 'passRate': 0.0, 'auditEventCount': 0, 'revisionCount': 0},
            'batchReports': [], 'topReasons': [], 'reviewers': [], 'recentEpisodes': [], 'recentRevisions': [], 'recentAuditRecords': [],
        }

    # ── 全部 episode（带 batch 预加载，避免 serialize 时 N+1）──
    episodes = _active_episode_query(db).options(joinedload(Episode.batch)).filter(Episode.batch_id.in_(scoped_batch_ids)).order_by(Episode.updated_at.desc()).all()
    scoped_episode_ids = {item.id for item in episodes}

    # ── SQL 聚合：episode 统计 ──
    ep_row = db.query(
        func.count(Episode.id).label('total'),
        func.coalesce(func.sum(case((Episode.sampled_for_qc == 1, 1), else_=0)), 0).label('sampled'),
        func.coalesce(func.sum(case((Episode.qc_status == 'done', 1), else_=0)), 0).label('done'),
        func.coalesce(func.sum(case((Episode.qc_result == 'fail', 1), else_=0)), 0).label('fail'),
        func.coalesce(func.sum(case((Episode.qc_result == 'pass', 1), else_=0)), 0).label('passed'),
    ).filter(Episode.batch_id.in_(scoped_batch_ids)).first()
    total_ep, sampled_ep, done_ep, fail_ep, pass_ep = ep_row

    # ── SQL 聚合：每 batch 的 fail / pass / done ──
    batch_ep_stats = {}
    for row in db.query(
        Episode.batch_id,
        func.coalesce(func.sum(case((Episode.qc_result == 'fail', 1), else_=0)), 0).label('fail_cnt'),
        func.coalesce(func.sum(case((Episode.qc_result == 'pass', 1), else_=0)), 0).label('pass_cnt'),
        func.coalesce(func.sum(case((Episode.qc_status == 'done', 1), else_=0)), 0).label('done_cnt'),
    ).filter(Episode.batch_id.in_(scoped_batch_ids)).group_by(Episode.batch_id).all():
        batch_ep_stats[row.batch_id] = (row.fail_cnt, row.pass_cnt, row.done_cnt)

    # ── SQL 聚合：每 batch 的 revision 数 ──
    batch_rev_counts = dict(
        db.query(Episode.batch_id, func.count(QcReviewRevision.id))
        .join(QcReviewRevision, QcReviewRevision.episode_id == Episode.id)
        .filter(Episode.batch_id.in_(scoped_batch_ids))
        .group_by(Episode.batch_id).all()
    )

    # ── SQL 聚合：每 batch 的 reviewer 数 ──
    batch_reviewer_counts = dict(
        db.query(Episode.batch_id, func.count(func.distinct(Episode.reviewer)))
        .filter(Episode.batch_id.in_(scoped_batch_ids), Episode.reviewer != '-')
        .group_by(Episode.batch_id).all()
    )

    # ── SQL：每 batch 最近 revision 时间 ──
    batch_latest_rev = dict(
        db.query(Episode.batch_id, func.max(QcReviewRevision.time))
        .join(QcReviewRevision, QcReviewRevision.episode_id == Episode.id)
        .filter(Episode.batch_id.in_(scoped_batch_ids))
        .group_by(Episode.batch_id).all()
    )

    # ── 审计事件（按 batch scope 过滤，不追 task 维度）──
    scoped_audits = db.query(AuditEvent).filter(
        AuditEvent.target.in_(scoped_batch_ids | scoped_episode_ids)
    ).order_by(AuditEvent.time.desc()).all()
    # 每 batch 审计计数
    batch_audit_counts: dict[str, int] = {}
    for audit in scoped_audits:
        if audit.target in scoped_batch_ids:
            batch_audit_counts[audit.target] = batch_audit_counts.get(audit.target, 0) + 1
        elif audit.target in scoped_episode_ids:
            # 找到该 episode 所属 batch
            for ep in episodes:
                if ep.id == audit.target:
                    batch_audit_counts[ep.batch_id] = batch_audit_counts.get(ep.batch_id, 0) + 1
                    break

    # ── Revision（按 batch scope 过滤）──
    scoped_revisions = db.query(QcReviewRevision).join(Episode).filter(
        Episode.batch_id.in_(scoped_batch_ids)
    ).order_by(QcReviewRevision.time.desc(), QcReviewRevision.revision_no.desc()).all()
    revision_total = len(scoped_revisions)
    audit_total = len(scoped_audits)

    # ── Reviewer 与 Reason 统计（已有 SQL 聚合，保持不变）──
    reviewer_rows = db.query(
        Episode.reviewer.label('name'),
        func.coalesce(func.sum(case((Episode.qc_status.in_(['assigned', 'in_review']), 1), else_=0)), 0).label('assigned'),
        func.coalesce(func.sum(case((Episode.qc_status == 'done', 1), else_=0)), 0).label('done'),
        func.coalesce(func.sum(case((Episode.qc_result == 'pass', 1), else_=0)), 0).label('passed'),
    ).filter(
        Episode.reviewer != '-',
        Episode.batch_id.in_(scoped_batch_ids),
    ).group_by(Episode.reviewer).order_by(Episode.reviewer.asc()).all()

    reason_counts = db.query(
        Episode.reason_code,
        func.count(Episode.id).label('count'),
    ).filter(
        Episode.reason_code != '-',
        Episode.batch_id.in_(scoped_batch_ids),
    ).group_by(Episode.reason_code).order_by(func.count(Episode.id).desc(), Episode.reason_code.asc()).all()
    total_reasons = sum(item.count for item in reason_counts)
    category_map = {item['reason']: item['category'] for item in reason_stats_payload()}

    # ── 构建 batch_reports（使用 SQL 聚合数据）──
    batch_reports = []
    for batch in scoped_batches:
        fail_cnt, pass_cnt, done_cnt = batch_ep_stats.get(batch.id, (0, 0, 0))
        rev_time = batch_latest_rev.get(batch.id)
        candidates = [t for t in (batch.imported_at, rev_time) if t is not None]
        latest_activity = max(candidates) if candidates else None
        batch_reports.append({
            'batchId': batch.id,
            'batchName': batch.name,
            'importedAt': format_time(batch.imported_at),
            'qcStatus': batch.qc_status,
            'dispatchMode': batch.dispatch_mode,
            'samplingRatio': batch.sampling_ratio,
            'episodeCount': batch.episode_count,
            'sampledEpisodeCount': batch.sampled_episode_count,
            'completedSampleCount': batch.completed_sample_count,
            'failEpisodeCount': fail_cnt,
            'passEpisodeCount': pass_cnt,
            'passRate': round((pass_cnt / done_cnt) * 100, 1) if done_cnt else 0.0,
            'topReason': batch.top_reason,
            'reviewerCount': batch_reviewer_counts.get(batch.id, 0),
            'auditEventCount': batch_audit_counts.get(batch.id, 0),
            'revisionCount': batch_rev_counts.get(batch.id, 0),
            'latestActivityAt': format_optional_time(latest_activity),
        })

    return {
        'generatedAt': format_time(datetime.utcnow()),
        'selectedBatchId': selected_batch_id,
        'summary': {
            'batchCount': len(scoped_batches),
            'episodeCount': total_ep or 0,
            'sampledEpisodeCount': sampled_ep or 0,
            'completedSampleCount': done_ep or 0,
            'failEpisodeCount': fail_ep or 0,
            'passEpisodeCount': pass_ep or 0,
            'passRate': round((pass_ep / done_ep) * 100, 1) if done_ep else 0.0,
            'auditEventCount': audit_total,
            'revisionCount': revision_total,
        },
        'batchReports': batch_reports,
        'topReasons': [
            {
                'reason': item.reason_code,
                'count': item.count,
                'ratio': round(item.count * 100 / total_reasons) if total_reasons else 0,
                'category': category_map.get(item.reason_code, 'Other'),
            }
            for item in reason_counts
        ],
        'reviewers': [
            {
                'name': item.name,
                'assigned': item.assigned,
                'done': item.done,
                'passRate': round((item.passed / item.done) * 100, 1) if item.done else 0.0,
            }
            for item in reviewer_rows
        ],
        'recentEpisodes': [serialize_episode(item) for item in episodes[:20]],
        'recentRevisions': [serialize_revision(item) for item in scoped_revisions[:40]],
        'recentAuditRecords': [serialize_audit(item) for item in scoped_audits[:60]],
    }


def build_history_export_payload(db: Session, selected_batch_id: str = 'all', scope: str = 'report') -> dict:
    history = history_payload(db)
    report = build_history_report_payload(db, selected_batch_id)
    batch_ids = {item['batchId'] for item in report['batchReports']}
    episode_ids = {item['id'] for item in history['episodes'] if item['batchId'] in batch_ids}
    episodes = history['episodes'] if selected_batch_id == 'all' else [item for item in history['episodes'] if item['batchId'] in batch_ids]
    revisions = history['qcRevisions'] if selected_batch_id == 'all' else [item for item in history['qcRevisions'] if item['batchId'] in batch_ids]
    audits = history['auditRecords'] if selected_batch_id == 'all' else [
        item for item in history['auditRecords']
        if item['target'] in batch_ids or item['target'] in episode_ids
    ]

    if scope == 'report':
        episodes = []
        revisions = []
        audits = []
    elif scope == 'episodes':
        audits = []
    elif scope == 'audits':
        episodes = []
        revisions = []

    return {
        'generatedAt': report['generatedAt'],
        'scope': scope,
        'selectedBatchId': selected_batch_id,
        'summary': report['summary'],
        'batchReports': report['batchReports'],
        'episodes': episodes,
        'qcRevisions': revisions,
        'auditRecords': audits,
    }


def reviewer_account_payload(db: Session) -> list[dict]:
    reviewers = db.query(User).filter(User.role == 'reviewer', User.is_active == 1).order_by(User.username.asc()).all()
    return [serialize_user(item) for item in reviewers]


def _active_qc_task_query(db: Session):
    return db.query(QcTask).filter(QcTask.is_active == 1)


def _task_counts_by_batch(db: Session, batch_ids: Iterable[str]) -> dict[str, dict[str, int]]:
    batch_ids = [item for item in batch_ids if item]
    if not batch_ids:
        return {}

    rows = db.query(
        QcTask.batch_id,
        QcTask.status,
        func.count(QcTask.id).label('count'),
    ).filter(
        QcTask.batch_id.in_(batch_ids),
        QcTask.is_active == 1,
    ).group_by(QcTask.batch_id, QcTask.status).all()

    counts = {
        batch_id: {
            'new': 0,
            'assigned': 0,
            'in_review': 0,
            'done': 0,
        }
        for batch_id in batch_ids
    }
    for row in rows:
        if row.batch_id not in counts:
            continue
        counts[row.batch_id][row.status] = row.count
    return counts


def _superseded_task_counts_by_batch(db: Session, batch_ids: Iterable[str]) -> dict[str, int]:
    batch_ids = [item for item in batch_ids if item]
    if not batch_ids:
        return {}

    rows = db.query(
        QcTask.batch_id,
        func.count(QcTask.id).label('count'),
    ).filter(
        QcTask.batch_id.in_(batch_ids),
        QcTask.is_active == 0,
    ).group_by(QcTask.batch_id).all()
    return {row.batch_id: row.count for row in rows}


def dispatch_preview_payload(batch: Batch, counts: dict[str, int] | None = None, superseded_count: int = 0) -> dict:
    counts = counts or {}
    new_count = counts.get('new', 0)
    assigned_count = counts.get('assigned', 0)
    in_review_count = counts.get('in_review', 0)
    done_count = counts.get('done', 0)
    return {
        'batchId': batch.id,
        'candidateEpisodeCount': batch.episode_count,
        'sampledEpisodeCount': batch.sampled_episode_count,
        'unsampledEpisodeCount': max(batch.episode_count - batch.sampled_episode_count, 0),
        'createdTaskCount': new_count + assigned_count + in_review_count + done_count,
        'assignedTaskCount': assigned_count,
        'inReviewTaskCount': in_review_count,
        'doneTaskCount': done_count,
        'supersededTaskCount': superseded_count,
        'pendingAssignCount': new_count,
        'dispatchMode': batch.dispatch_mode,
        'samplingRatio': batch.sampling_ratio,
        'activeDispatchGeneration': batch.active_dispatch_generation,
    }


def task_pool_payload(db: Session, current_user: User | None = None) -> dict:
    is_reviewer = bool(current_user and current_user.role == 'reviewer')

    tasks_query = _active_qc_task_query(db)
    if is_reviewer:
        tasks_query = tasks_query.filter(QcTask.assignee == current_user.name)
    tasks = tasks_query.order_by(QcTask.created_at.desc()).all()

    if is_reviewer:
        own_batch_ids = {task.batch_id for task in tasks if task.batch_id}
        batches = (
            db.query(Batch).filter(Batch.id.in_(own_batch_ids)).order_by(Batch.imported_at.desc()).all()
            if own_batch_ids else []
        )
    else:
        batches = db.query(Batch).order_by(Batch.imported_at.desc()).all()

    counts_by_batch = _task_counts_by_batch(db, [item.id for item in batches])
    superseded_by_batch = _superseded_task_counts_by_batch(db, [item.id for item in batches])
    return {
        'batches': _serialize_batches(db, batches),
        'dispatchPreviews': [dispatch_preview_payload(item, counts_by_batch.get(item.id), superseded_by_batch.get(item.id, 0)) for item in batches],
        'qcTasks': [serialize_task(item, current_user) for item in tasks],
        # reviewer 不应看到他人工作量与账号目录（派发素材，仅管理员可见）
        'reviewerWorkloads': [] if is_reviewer else reviewer_workload_payload(db),
        'reviewerAccounts': [] if is_reviewer else reviewer_account_payload(db),
    }


def manual_qc_context_payload(db: Session, episode_id: str, current_user: User | None = None) -> dict:
    episode = db.query(Episode).filter(Episode.id == episode_id).one()
    revisions = db.query(QcReviewRevision).filter(QcReviewRevision.episode_id == episode_id).order_by(QcReviewRevision.revision_no.desc()).all()
    task = db.query(QcTask).filter(QcTask.episode_id == episode_id, QcTask.is_active == 1).order_by(QcTask.dispatch_generation.desc(), QcTask.created_at.desc()).first()
    review_lock = review_lock_payload(task, current_user) if task else {
        'isLocked': False,
        'isMine': False,
        'ownerUserId': '',
        'ownerName': '',
        'acquiredAt': None,
        'expiresAt': None,
        'version': 0,
    }
    view_mode, can_claim, can_submit = _manual_qc_permissions(task, current_user)
    real_context = _build_real_manual_qc_context(db, episode_id)

    if real_context:
        episode.duration_sec = real_context['durationSec']
        episode.frame_count = real_context['frameCount']
        return {
            'episode': {
                **serialize_episode(episode),
                'durationSec': real_context['durationSec'],
                'frameCount': real_context['frameCount'],
                'fps': real_context['fps'],
            },
            'l3V2': real_context.get('l3V2'),
            'revisions': [serialize_revision(item) for item in revisions],
            'reviewLock': review_lock,
            'media': _manual_qc_media(db, episode_id, current_user),
            'taskStatus': task.status if task else None,
            'viewMode': view_mode,
            'canClaim': can_claim,
            'canSubmit': can_submit,
        }

    return {
        'episode': {
            **serialize_episode(episode),
            'fps': episode.frame_count / episode.duration_sec if (episode.frame_count and episode.duration_sec) else 0.0,
        },
        'l3V2': None,
        'revisions': [serialize_revision(item) for item in revisions],
        'reviewLock': review_lock,
        'media': _manual_qc_media(db, episode_id, current_user),
        'taskStatus': task.status if task else None,
        'viewMode': view_mode,
        'canClaim': can_claim,
        'canSubmit': can_submit,
    }


def reviewer_dashboard_payload(db: Session, reviewer_id: str) -> dict:
    user = db.query(User).filter(User.id == reviewer_id).first()
    reviewer_name = user.name if user else ''

    tasks = db.query(QcTask).filter(
        QcTask.assignee == reviewer_name,
        QcTask.is_active == 1,
    ).all()

    stats = reviewer_dashboard_stats_payload(tasks)
    batch_groups = _reviewer_batch_groups_payload(db, tasks)
    next_task = _reviewer_next_task_payload(tasks)

    return {
        'stats': stats,
        'batchGroups': batch_groups,
        'nextTask': next_task,
    }


def reviewer_dashboard_stats_payload(tasks: list[QcTask]) -> dict:
    pending = sum(1 for t in tasks if t.status in ('new', 'assigned'))
    in_review = sum(1 for t in tasks if t.status == 'in_review')
    today = datetime.now(timezone.utc).date()
    done_today = sum(1 for t in tasks if t.status == 'done' and t.updated_at and t.updated_at.date() == today)
    total = len(tasks)
    return {
        'pendingCount': pending,
        'inReviewCount': in_review,
        'doneTodayCount': done_today,
        'totalAssignedCount': total,
    }


def _reviewer_batch_groups_payload(db: Session, tasks: list[QcTask]) -> list[dict]:
    batch_ids = list({t.batch_id for t in tasks})
    if not batch_ids:
        return []
    batches = {b.id: b for b in db.query(Batch).filter(Batch.id.in_(batch_ids)).all()}
    groups: dict[str, dict] = {}
    for t in tasks:
        g = groups.setdefault(t.batch_id, {
            'batchId': t.batch_id,
            'batchName': batches.get(t.batch_id, Batch()).name,
            'pendingCount': 0,
            'doneCount': 0,
            'totalCount': 0,
        })
        g['totalCount'] += 1
        if t.status in ('new', 'assigned'):
            g['pendingCount'] += 1
        elif t.status == 'done':
            g['doneCount'] += 1
    return list(groups.values())


def _reviewer_next_task_payload(tasks: list[QcTask]) -> dict | None:
    pending = sorted(
        [t for t in tasks if t.status in ('new', 'assigned')],
        key=lambda t: t.created_at or datetime.min.replace(tzinfo=timezone.utc),
    )
    if not pending:
        return None
    t = pending[0]
    return {
        'taskId': t.id,
        'episodeId': t.episode_id,
        'batchName': t.batch_name or '',
    }


def home_payload(db: Session, current_user: User) -> dict:
    return {
        'dashboard': dashboard_payload(db, current_user),
        'database': database_payload(db, page_size=20),
        'taskPool': task_pool_payload(db),
        'history': history_payload(db),
    }
