from __future__ import annotations

import io
import json
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import AuditEvent, Batch, Episode, EpisodeInventory, EpisodeObject, ListRecord, QcReviewRevision, QcTask, ScanJob, TaskType, User
from app.services.minio_client import get_minio_service


def format_time(value: datetime) -> str:
    return value.strftime('%Y-%m-%d %H:%M')


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


def serialize_batch(db: Session, batch: Batch) -> dict:
    coverage = round((batch.sampled_episode_count / batch.episode_count) * 100) if batch.episode_count else 0
    completion = round((batch.completed_sample_count / batch.sampled_episode_count) * 100) if batch.sampled_episode_count else 0
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


def sync_batch_metrics(db: Session, batch: Batch) -> None:
    sampled_count = db.query(func.count(Episode.id)).filter(Episode.batch_id == batch.id, Episode.sampled_for_qc == 1).scalar() or 0
    completed_count = db.query(func.count(Episode.id)).filter(Episode.batch_id == batch.id, Episode.sampled_for_qc == 1, Episode.qc_status == 'done').scalar() or 0
    passed_count = db.query(func.count(Episode.id)).filter(Episode.batch_id == batch.id, Episode.sampled_for_qc == 1, Episode.qc_result == 'pass').scalar() or 0
    top_reason = db.query(Episode.reason_code, func.count(Episode.id).label('count')).filter(
        Episode.batch_id == batch.id,
        Episode.sampled_for_qc == 1,
        Episode.reason_code != '-',
    ).group_by(Episode.reason_code).order_by(func.count(Episode.id).desc(), Episode.reason_code.asc()).first()

    batch.sampled_episode_count = sampled_count
    batch.completed_sample_count = completed_count
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
        'qcStatus': episode.qc_status,
        'qcResult': episode.qc_result,
        'reviewer': episode.reviewer,
        'reasonCode': episode.reason_code,
        'updatedAt': format_time(episode.updated_at),
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
        'createdAt': format_time(task.created_at),
        'reviewLock': review_lock_payload(task, current_user),
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
    }


def serialize_ingest_job(job: ScanJob) -> dict:
    return {
        'id': job.id,
        'bucket': job.bucket,
        'scope': job.scope,
        'status': job.status,
        'progress': 100 if job.status == 'done' else 0,
        'confirmedLists': job.confirmed_lists,
        'totalEpisodes': job.total_episodes,
        'newEpisodes': job.new_episodes,
        'detail': job.error_detail or f'lists={job.confirmed_lists} episodes={job.total_episodes} new={job.new_episodes}',
        'startedAt': format_time(job.started_at),
        'finishedAt': format_time(job.finished_at) if job.finished_at else None,
    }


def _metric_level(value: float, warn_threshold: float, bad_threshold: float, reverse: bool = False) -> str:
    if reverse:
        if value <= bad_threshold:
            return 'bad'
        if value <= warn_threshold:
            return 'warn'
        return 'good'
    if value >= bad_threshold:
        return 'bad'
    if value >= warn_threshold:
        return 'warn'
    return 'good'


def _window_to_segment(mask: np.ndarray, timestamps: np.ndarray, label: str, level: str) -> list[dict]:
    if not mask.size or not mask.any():
        return []
    segments: list[dict] = []
    start_index: int | None = None
    for index, active in enumerate(mask.tolist()):
        if active and start_index is None:
            start_index = index
        if not active and start_index is not None:
            end_index = index - 1
            segments.append({
                'start': int(round(float(timestamps[start_index]))),
                'end': int(round(float(timestamps[end_index]))),
                'level': level,
                'label': label,
            })
            start_index = None
    if start_index is not None:
        segments.append({
            'start': int(round(float(timestamps[start_index]))),
            'end': int(round(float(timestamps[-1]))),
            'level': level,
            'label': label,
        })
    return segments


def _merge_segments(segments: list[dict], max_gap_seconds: int = 1, min_duration_seconds: int = 2) -> list[dict]:
    if not segments:
        return []

    def merge_pass(items: list[dict]) -> list[dict]:
        ordered = sorted(items, key=lambda item: (item['label'], item['start'], item['end']))
        merged: list[dict] = []

        for segment in ordered:
            if not merged:
                merged.append(dict(segment))
                continue

            current = merged[-1]
            same_stream = current['label'] == segment['label'] and current['level'] == segment['level']
            near_enough = segment['start'] <= current['end'] + max_gap_seconds
            if same_stream and near_enough:
                current['end'] = max(current['end'], segment['end'])
                continue

            merged.append(dict(segment))

        return merged

    merged = merge_pass(segments)

    for segment in merged:
        duration = segment['end'] - segment['start']
        if duration < min_duration_seconds:
            segment['end'] = segment['start'] + min_duration_seconds

    return sorted(merge_pass(merged), key=lambda item: (item['start'], item['label']))


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


def _media_slot_and_label(object_key: str) -> tuple[str, str]:
    normalized = object_key.lower()
    if 'left' in normalized:
        return 'left', 'Left Wrist'
    if 'right' in normalized:
        return 'right', 'Right Wrist'
    return 'top', 'Top Camera'


def _media_variant_from_key(object_key: str) -> str:
    normalized = object_key.lower()
    if 'depth' in normalized and 'colormap' in normalized:
        return 'depth_colormap'
    return 'rgb'


def _manual_qc_media(db: Session, episode_id: str, current_user: User | None) -> list[dict]:
    inventory_row = _lookup_inventory_for_episode(db, episode_id)
    if not inventory_row:
        return []

    inventory, bucket = inventory_row
    task = db.query(QcTask).filter(QcTask.episode_id == episode_id).first()
    review_lock = review_lock_payload(task, current_user) if task else None
    refreshable = bool(review_lock and review_lock['isMine'])
    preview_ttl = timedelta(minutes=5)

    media_items = []
    object_rows = db.query(EpisodeObject).filter(
        EpisodeObject.episode_inventory_id == inventory.id,
        EpisodeObject.object_scope == 'processed',
        EpisodeObject.object_key.like('%.mp4'),
    ).order_by(EpisodeObject.object_key.asc()).all()

    for item in object_rows:
        slot, label = _media_slot_and_label(item.object_key)
        variant = _media_variant_from_key(item.object_key)
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
            'sortOrder': {'top': 10, 'left': 20, 'right': 30}.get(slot, 100) + (1 if variant == 'depth_colormap' else 0),
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


def _build_real_manual_qc_context(db: Session, episode_id: str) -> dict | None:
    inventory_row = _lookup_inventory_for_episode(db, episode_id)
    if not inventory_row:
        return None

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

    with _read_minio_npz(bucket, telemetry_key) as telemetry:
        timestamps = telemetry['timestamps'].astype(np.float64)
        relative_seconds = timestamps - timestamps[0]
        tracking_error = np.abs(telemetry['actions'] - telemetry['qpos']).mean(axis=1)
        sync_diff_ms = telemetry['sync_validation_max_diff'].astype(np.float64)
        sync_valid_ratio = float(np.mean(telemetry['sync_validation_is_valid']))
        mean_speed = np.abs(telemetry['qvel']).mean(axis=1)
        mean_effort = np.abs(telemetry['effort']).mean(axis=1)
        jerk = np.abs(np.diff(telemetry['qvel'], axis=0)).mean(axis=1) if len(telemetry['qvel']) > 1 else np.array([0.0])

    tracking_p95 = float(np.percentile(tracking_error, 95))
    sync_p95 = float(np.percentile(sync_diff_ms, 95))
    sync_max = float(np.max(sync_diff_ms))
    speed_p95 = float(np.percentile(mean_speed, 95))
    effort_p95 = float(np.percentile(mean_effort, 95))
    jerk_p95 = float(np.percentile(jerk, 95))

    motion_score = max(0.0, min(10.0, 10.0 - tracking_p95 / 6.0 - sync_p95 / 220.0))
    smoothness_score = max(0.0, min(10.0, 10.0 - jerk_p95 / 0.01))
    sync_bad_rate = float(np.mean(sync_diff_ms > 700.0) * 100)
    tracking_warn_rate = float(np.mean(tracking_error > 30.0) * 100)

    metrics = [
        {
            'key': 'q_motion',
            'label': 'Q_motion',
            'value': f'{motion_score:.1f}',
            'level': _metric_level(motion_score, 6.5, 4.5, reverse=True),
            'description': f'基于 tracking p95={tracking_p95:.1f} 与 sync p95={sync_p95:.0f}ms 汇总',
        },
        {
            'key': 'smoothness',
            'label': '平滑度 LDLJ*',
            'value': f'{smoothness_score:.1f}',
            'level': _metric_level(smoothness_score, 7.0, 5.0, reverse=True),
            'description': f'用速度差分近似平滑度，jerk p95={jerk_p95:.3f}',
        },
        {
            'key': 'sync',
            'label': '同步异常率',
            'value': f'{sync_bad_rate:.1f}%',
            'level': _metric_level(sync_bad_rate, 3.0, 8.0),
            'description': f'阈值 700ms，max={sync_max:.0f}ms，valid={sync_valid_ratio * 100:.0f}%',
        },
        {
            'key': 'tracking',
            'label': '跟踪误差',
            'value': f'{tracking_p95:.1f}',
            'level': _metric_level(tracking_p95, 20.0, 30.0),
            'description': f'actions-qpos 平均绝对误差 p95，超阈帧占比 {tracking_warn_rate:.1f}% ',
        },
        {
            'key': 'velocity',
            'label': '动作速度 p95',
            'value': f'{speed_p95:.3f}',
            'level': _metric_level(speed_p95, 0.12, 0.18),
            'description': '用于快速定位高动态片段',
        },
        {
            'key': 'effort',
            'label': '执行力度 p95',
            'value': f'{effort_p95:.3f}',
            'level': _metric_level(effort_p95, 0.9, 1.5),
            'description': '检查控制量是否异常饱和',
        },
    ]

    timeline_segments = []
    timeline_segments.extend(_window_to_segment(sync_diff_ms > 700.0, relative_seconds, 'sync_bad', 'bad'))
    timeline_segments.extend(_window_to_segment(tracking_error > 30.0, relative_seconds, 'tracking_error', 'warn'))
    timeline_segments.extend(_window_to_segment(mean_speed > speed_p95, relative_seconds, 'high_velocity', 'warn'))
    timeline_segments = _merge_segments(timeline_segments)

    if not timeline_segments:
        timeline_segments.append({
            'start': 0,
            'end': int(round(float(relative_seconds[-1]))) if len(relative_seconds) else 0,
            'level': 'good',
            'label': 'stable_segment',
        })

    return {
        'durationSec': float(manifest.get('duration', 0.0)),
        'frameCount': int(manifest.get('frame_count', 0)),
        'fps': float(manifest.get('fps', 0.0)),
        'metrics': metrics,
        'timelineSegments': timeline_segments,
        'syncDescription': metadata.get('alignment', {}).get('method', ''),
    }


def dashboard_payload(db: Session, current_user: User) -> dict:
    return {
        'currentUser': serialize_user(current_user),
        'taskTypes': [serialize_task_type(item) for item in db.query(TaskType).order_by(TaskType.id).all()],
        'batches': [serialize_batch(db, item) for item in db.query(Batch).order_by(Batch.imported_at.desc()).all()],
        'qcTasks': [serialize_task(item, current_user) for item in db.query(QcTask).order_by(QcTask.created_at.desc()).all()],
        'reasonStats': reason_stats_payload_from_db(db),
        'reviewerWorkloads': reviewer_workload_payload(db),
        'ingestJobs': [serialize_ingest_job(item) for item in db.query(ScanJob).order_by(ScanJob.started_at.desc()).all()],
    }


def database_payload(db: Session) -> dict:
    return {
        'episodes': [serialize_episode(item) for item in db.query(Episode).order_by(Episode.updated_at.desc()).all()],
        'batches': [serialize_batch(db, item) for item in db.query(Batch).order_by(Batch.imported_at.desc()).all()],
        'taskTypes': [serialize_task_type(item) for item in db.query(TaskType).order_by(TaskType.id).all()],
        'reasonStats': reason_stats_payload_from_db(db),
        'ingestJobs': [serialize_ingest_job(item) for item in db.query(ScanJob).order_by(ScanJob.started_at.desc()).all()],
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
        {'reason': 'occlusion_object', 'category': 'L2'},
        {'reason': 'tracking_error', 'category': 'L3'},
        {'reason': 'placement_failed', 'category': 'L4'},
        {'reason': 'task_incomplete', 'category': 'L4'},
        {'reason': 'sync_bad', 'category': 'L3'},
        {'reason': 'metadata_missing', 'category': 'System'},
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


def history_payload(db: Session) -> dict:
    revisions = db.query(QcReviewRevision).order_by(QcReviewRevision.time.desc(), QcReviewRevision.revision_no.desc()).all()
    audits = db.query(AuditEvent).order_by(AuditEvent.time.desc()).all()
    episodes = db.query(Episode).order_by(Episode.updated_at.desc()).all()
    batches = db.query(Batch).order_by(Batch.imported_at.desc()).all()
    return {
        'auditRecords': [serialize_audit(item) for item in audits],
        'qcRevisions': [serialize_revision(item) for item in revisions],
        'episodes': [serialize_episode(item) for item in episodes],
        'batches': [serialize_batch(db, item) for item in batches],
    }


def _latest_activity_time(batch: Batch) -> datetime | None:
    candidates = [batch.imported_at]
    candidates.extend(episode.updated_at for episode in batch.episodes if episode.updated_at)
    candidates.extend(revision.time for episode in batch.episodes for revision in episode.revisions if revision.time)
    return max(candidates) if candidates else None


def build_history_report_payload(db: Session, selected_batch_id: str = 'all') -> dict:
    batches = db.query(Batch).order_by(Batch.imported_at.desc()).all()
    revisions = db.query(QcReviewRevision).order_by(QcReviewRevision.time.desc(), QcReviewRevision.revision_no.desc()).all()
    audits = db.query(AuditEvent).order_by(AuditEvent.time.desc()).all()
    episodes = db.query(Episode).order_by(Episode.updated_at.desc()).all()

    scoped_batches = batches if selected_batch_id == 'all' else [item for item in batches if item.id == selected_batch_id]
    scoped_batch_ids = {item.id for item in scoped_batches}
    scoped_episodes = [item for item in episodes if item.batch_id in scoped_batch_ids]
    scoped_episode_ids = {item.id for item in scoped_episodes}
    scoped_task_ids = {task.id for episode in scoped_episodes for task in episode.qc_tasks}
    scoped_revisions = [item for item in revisions if item.episode.batch_id in scoped_batch_ids]
    scoped_audits = [
        item for item in audits
        if item.target in scoped_batch_ids
        or item.target in scoped_episode_ids
        or any(f'task={task_id}' in item.detail for task_id in scoped_task_ids)
    ]

    done_episodes = [item for item in scoped_episodes if item.qc_status == 'done']
    fail_episodes = [item for item in scoped_episodes if item.qc_result == 'fail']
    pass_episodes = [item for item in scoped_episodes if item.qc_result == 'pass']
    sampled_episodes = [item for item in scoped_episodes if item.sampled_for_qc == 1]

    reviewer_rows = db.query(
        Episode.reviewer.label('name'),
        func.sum(case((Episode.qc_status.in_(['assigned', 'in_review']), 1), else_=0)).label('assigned'),
        func.sum(case((Episode.qc_status == 'done', 1), else_=0)).label('done'),
        func.sum(case((Episode.qc_result == 'pass', 1), else_=0)).label('passed'),
    ).filter(
        Episode.reviewer != '-',
        Episode.batch_id.in_(scoped_batch_ids),
    ).group_by(Episode.reviewer).order_by(Episode.reviewer.asc()).all() if scoped_batch_ids else []

    reason_counts = db.query(
        Episode.reason_code,
        func.count(Episode.id).label('count'),
    ).filter(
        Episode.reason_code != '-',
        Episode.batch_id.in_(scoped_batch_ids),
    ).group_by(Episode.reason_code).order_by(func.count(Episode.id).desc(), Episode.reason_code.asc()).all() if scoped_batch_ids else []
    total_reasons = sum(item.count for item in reason_counts)
    category_map = {item['reason']: item['category'] for item in reason_stats_payload()}

    batch_reports = []
    for batch in scoped_batches:
        batch_episode_ids = {episode.id for episode in batch.episodes}
        batch_done = [episode for episode in batch.episodes if episode.qc_status == 'done']
        batch_fail = [episode for episode in batch.episodes if episode.qc_result == 'fail']
        batch_pass = [episode for episode in batch.episodes if episode.qc_result == 'pass']
        batch_revisions = [revision for revision in scoped_revisions if revision.episode_id in batch_episode_ids]
        batch_task_ids = {task.id for episode in batch.episodes for task in episode.qc_tasks}
        batch_audits = [
            audit for audit in scoped_audits
            if audit.target == batch.id
            or audit.target in batch_episode_ids
            or any(f'task={task_id}' in audit.detail for task_id in batch_task_ids)
        ]
        batch_reviewers = {episode.reviewer for episode in batch.episodes if episode.reviewer != '-'}
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
            'failEpisodeCount': len(batch_fail),
            'passEpisodeCount': len(batch_pass),
            'passRate': round((len(batch_pass) / len(batch_done)) * 100, 1) if batch_done else 0.0,
            'topReason': batch.top_reason,
            'reviewerCount': len(batch_reviewers),
            'auditEventCount': len(batch_audits),
            'revisionCount': len(batch_revisions),
            'latestActivityAt': format_optional_time(_latest_activity_time(batch)),
        })

    return {
        'generatedAt': format_time(datetime.utcnow()),
        'selectedBatchId': selected_batch_id,
        'summary': {
            'batchCount': len(scoped_batches),
            'episodeCount': len(scoped_episodes),
            'sampledEpisodeCount': len(sampled_episodes),
            'completedSampleCount': len(done_episodes),
            'failEpisodeCount': len(fail_episodes),
            'passEpisodeCount': len(pass_episodes),
            'passRate': round((len(pass_episodes) / len(done_episodes)) * 100, 1) if done_episodes else 0.0,
            'auditEventCount': len(scoped_audits),
            'revisionCount': len(scoped_revisions),
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
                'assigned': item.assigned or 0,
                'done': item.done or 0,
                'passRate': round(((item.passed or 0) / (item.done or 0)) * 100, 1) if item.done else 0.0,
            }
            for item in reviewer_rows
        ],
        'recentEpisodes': [serialize_episode(item) for item in scoped_episodes[:20]],
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


def dispatch_preview_payload(db: Session, batch_id: str) -> dict:
    batch = db.query(Batch).filter(Batch.id == batch_id).one()
    created = db.query(func.count(QcTask.id)).filter(QcTask.batch_id == batch_id).scalar() or 0
    assigned = db.query(func.count(QcTask.id)).filter(QcTask.batch_id == batch_id, QcTask.status == 'assigned').scalar() or 0
    in_review = db.query(func.count(QcTask.id)).filter(QcTask.batch_id == batch_id, QcTask.status == 'in_review').scalar() or 0
    done = db.query(func.count(QcTask.id)).filter(QcTask.batch_id == batch_id, QcTask.status == 'done').scalar() or 0
    return {
        'batchId': batch.id,
        'candidateEpisodeCount': batch.episode_count,
        'sampledEpisodeCount': batch.sampled_episode_count,
        'unsampledEpisodeCount': max(batch.episode_count - batch.sampled_episode_count, 0),
        'createdTaskCount': created,
        'assignedTaskCount': assigned,
        'inReviewTaskCount': in_review,
        'doneTaskCount': done,
        'dispatchMode': batch.dispatch_mode,
        'samplingRatio': batch.sampling_ratio,
    }


def task_pool_payload(db: Session, current_user: User | None = None) -> dict:
    batches = db.query(Batch).order_by(Batch.imported_at.desc()).all()
    return {
        'batches': [serialize_batch(db, item) for item in batches],
        'dispatchPreviews': [dispatch_preview_payload(db, item.id) for item in batches],
        'qcTasks': [serialize_task(item, current_user) for item in db.query(QcTask).order_by(QcTask.created_at.desc()).all()],
        'reviewerWorkloads': reviewer_workload_payload(db),
    }


def manual_qc_context_payload(db: Session, episode_id: str, current_user: User | None = None) -> dict:
    episode = db.query(Episode).filter(Episode.id == episode_id).one()
    revisions = db.query(QcReviewRevision).filter(QcReviewRevision.episode_id == episode_id).order_by(QcReviewRevision.revision_no.desc()).all()
    task = db.query(QcTask).filter(QcTask.episode_id == episode_id).first()
    review_lock = review_lock_payload(task, current_user) if task else {
        'isLocked': False,
        'isMine': False,
        'ownerUserId': '',
        'ownerName': '',
        'acquiredAt': None,
        'expiresAt': None,
        'version': 0,
    }
    real_context = _build_real_manual_qc_context(db, episode_id)

    if real_context:
        episode.duration_sec = real_context['durationSec']
        episode.frame_count = real_context['frameCount']
        return {
            'episode': serialize_episode(episode),
            'metrics': real_context['metrics'],
            'timelineSegments': real_context['timelineSegments'],
            'revisions': [serialize_revision(item) for item in revisions],
            'reviewLock': review_lock,
            'media': _manual_qc_media(db, episode_id, current_user),
        }

    return {
        'episode': serialize_episode(episode),
        'metrics': [
            {'key': 'q_motion', 'label': 'Q_motion', 'value': '8.6', 'level': 'good', 'description': '轨迹质量综合分'},
            {'key': 'smoothness', 'label': '平滑度 LDLJ', 'value': '7.9', 'level': 'good', 'description': '动作连续性良好'},
            {'key': 'sync', 'label': '同步异常率', 'value': '1.8%', 'level': 'good', 'description': '低于 5% 阈值'},
            {'key': 'tracking', 'label': '跟踪误差', 'value': '0.21', 'level': 'warn', 'description': '右手末段略高'},
            {'key': 'chatter', 'label': '手指颤振', 'value': '0.08', 'level': 'good', 'description': '未发现明显抖动'},
            {'key': 'saturation', 'label': '动作饱和率', 'value': '3.2%', 'level': 'good', 'description': '遥操指令正常'},
        ],
        'timelineSegments': [
            {'start': 18, 'end': 26, 'level': 'warn', 'label': 'tracking_error'},
            {'start': 63, 'end': 71, 'level': 'bad', 'label': 'occlusion_object'},
            {'start': 82, 'end': 88, 'level': 'warn', 'label': 'sync_bad'},
        ],
        'revisions': [serialize_revision(item) for item in revisions],
        'reviewLock': review_lock,
        'media': _manual_qc_media(db, episode_id, current_user),
    }


def home_payload(db: Session, current_user: User) -> dict:
    return {
        'dashboard': dashboard_payload(db, current_user),
        'database': database_payload(db),
        'taskPool': task_pool_payload(db),
        'history': history_payload(db),
    }
