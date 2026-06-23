from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuditEvent, Batch, Episode, IngestJob, TaskType, User
from app.services.payloads import sync_batch_metrics

settings = get_settings()
ALLOWED_SCAN_ROOTS = tuple(path.resolve() for path in [settings.sample_processed_root, settings.collection_data_root / 'process'])


def ensure_active_user(user: User) -> User:
    if not user.is_active:
        raise ValueError('账号已停用')
    return user


def require_roles(user: User, *roles: str) -> User:
    ensure_active_user(user)
    if roles and user.role not in roles:
        raise PermissionError('无权限执行该操作')
    return user


def serialize_ingest_job(job: IngestJob) -> dict:
    return {
        'id': job.id,
        'batchId': job.batch_id,
        'batchName': job.batch_name,
        'sourcePath': job.source_path,
        'status': job.status,
        'progress': job.progress,
        'episodes': job.episodes,
        'importedEpisodes': job.imported_episodes,
        'skippedEpisodes': job.skipped_episodes,
        'detail': job.detail,
        'startedAt': job.started_at.strftime('%Y-%m-%d %H:%M'),
        'finishedAt': job.finished_at.strftime('%Y-%m-%d %H:%M') if job.finished_at else None,
    }


def list_ingest_jobs(db: Session) -> list[dict]:
    jobs = db.query(IngestJob).order_by(IngestJob.started_at.desc()).all()
    return [serialize_ingest_job(job) for job in jobs]


def _resolve_scan_root(source_path: str) -> Path:
    if not source_path.strip():
        raise ValueError('sourcePath 不能为空')
    resolved = Path(source_path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError('扫描目录不存在')
    for allowed_root in ALLOWED_SCAN_ROOTS:
        try:
            resolved.relative_to(allowed_root)
            return resolved
        except ValueError:
            continue
    allowed = ', '.join(str(item) for item in ALLOWED_SCAN_ROOTS)
    raise ValueError(f'扫描目录不在允许范围内: {allowed}')


def _discover_episode_dirs(source_root: Path) -> list[Path]:
    episode_dirs: list[Path] = []
    if (source_root / 'manifest.json').exists() and (source_root / 'metadata.json').exists() and (source_root / 'telemetry.npz').exists():
        return [source_root]

    for child in sorted(source_root.iterdir()):
        if not child.is_dir():
            continue
        if (child / 'manifest.json').exists() and (child / 'metadata.json').exists() and (child / 'telemetry.npz').exists():
            episode_dirs.append(child)
    return episode_dirs


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _fingerprint(path: Path) -> str:
    payload = hashlib.sha256()
    for name in ['manifest.json', 'metadata.json', 'telemetry.npz']:
        file_path = path / name
        stat = file_path.stat()
        payload.update(str(file_path.resolve()).encode('utf-8'))
        payload.update(str(stat.st_size).encode('utf-8'))
        payload.update(str(stat.st_mtime_ns).encode('utf-8'))
    return payload.hexdigest()


def _derive_task_type(metadata: dict) -> tuple[str, str, str]:
    arm_model = (metadata.get('device') or {}).get('arm', {}).get('model') or 'Unknown Arm'
    device_type = (metadata.get('device') or {}).get('device', {}).get('type') or 'unknown'
    task_type_id = hashlib.sha1(f'{device_type}:{arm_model}'.encode('utf-8')).hexdigest()[:12]
    task_type_name = arm_model
    description = f'{device_type} / {arm_model}'
    return task_type_id, task_type_name, description


def _upsert_task_type(db: Session, metadata: dict) -> TaskType:
    task_type_id, name, description = _derive_task_type(metadata)
    task_type = db.query(TaskType).filter(TaskType.id == task_type_id).first()
    if not task_type:
        task_type = TaskType(
            id=task_type_id,
            name=name,
            description=description,
            total_batches=0,
            total_episodes=0,
        )
        db.add(task_type)
    else:
        task_type.name = name
        task_type.description = description
    return task_type


def _refresh_task_type_totals(db: Session, task_type: TaskType) -> None:
    batches = db.query(Batch).filter(Batch.task_type_id == task_type.id).all()
    task_type.total_batches = len(batches)
    task_type.total_episodes = sum(item.episode_count for item in batches)


def _batch_identity(source_root: Path) -> tuple[str, str]:
    source_hash = hashlib.sha1(str(source_root.resolve()).encode('utf-8')).hexdigest()[:12]
    batch_id = f'batch_{source_hash}'
    batch_name = source_root.name or batch_id
    return batch_id, batch_name


def run_ingest_scan(db: Session, *, source_path: str, batch_name: str, operator: User) -> IngestJob:
    require_roles(operator, 'admin', 'qc_manager')
    source_root = _resolve_scan_root(source_path)
    episode_dirs = _discover_episode_dirs(source_root)
    batch_id, default_batch_name = _batch_identity(source_root)
    job_id = f'ingest_{batch_id}_{int(datetime.utcnow().timestamp())}'

    job = IngestJob(
        id=job_id,
        batch_id=batch_id,
        batch_name=(batch_name or default_batch_name).strip() or default_batch_name,
        source_path=str(source_root),
        status='scanning',
        progress=0,
        episodes=0,
        imported_episodes=0,
        skipped_episodes=0,
        detail='',
        started_at=datetime.utcnow(),
        finished_at=None,
    )
    db.add(job)
    db.flush()

    if not episode_dirs:
        job.status = 'failed'
        job.detail = '未发现包含 manifest.json / metadata.json / telemetry.npz 的 processed episode'
        job.finished_at = datetime.utcnow()
        db.add(AuditEvent(
            id=f'audit_ingest_{job.id}',
            operator=operator.name,
            action='扫描入库失败',
            target=job.id,
            detail=job.detail,
            time=datetime.utcnow(),
        ))
        db.commit()
        return job

    first_metadata = _load_json(episode_dirs[0] / 'metadata.json')
    task_type = _upsert_task_type(db, first_metadata)
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        batch = Batch(
            id=batch_id,
            task_type_id=task_type.id,
            name=job.batch_name,
            imported_at=datetime.utcnow(),
            episode_count=0,
            sampled_episode_count=0,
            completed_sample_count=0,
            dispatch_mode='sampled',
            sampling_ratio=25,
            qc_status='new',
            pass_rate=0.0,
            top_reason='-',
            storage_path=str(source_root),
        )
        db.add(batch)
    else:
        batch.name = job.batch_name
        batch.task_type_id = task_type.id
        batch.storage_path = str(source_root)

    imported = 0
    skipped = 0
    total = len(episode_dirs)

    for index, episode_dir in enumerate(episode_dirs, start=1):
        manifest = _load_json(episode_dir / 'manifest.json')
        metadata = _load_json(episode_dir / 'metadata.json')
        source_hash = _fingerprint(episode_dir)
        source_episode_id = str(manifest.get('episode_id') or episode_dir.name)
        episode_id = f'{batch_id}_{source_episode_id}'
        task_name = ((metadata.get('device') or {}).get('arm', {}) or {}).get('model') or task_type.name

        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if episode and episode.source_hash == source_hash:
            skipped += 1
        else:
            if not episode:
                episode = Episode(
                    id=episode_id,
                    batch_id=batch.id,
                    task_name=task_name,
                    duration_sec=float(manifest.get('duration') or metadata.get('conversion', {}).get('duration') or 0.0),
                    frame_count=int(manifest.get('frame_count') or metadata.get('conversion', {}).get('frame_count') or 0),
                    qc_status='new',
                    qc_result='pending',
                    reviewer='-',
                    reason_code='-',
                    source_path=str(episode_dir),
                    source_hash=source_hash,
                    ingest_status='indexed',
                    updated_at=datetime.utcnow(),
                    in_candidate_pool=1,
                    sampled_for_qc=0,
                )
                db.add(episode)
            else:
                episode.batch_id = batch.id
                episode.task_name = task_name
                episode.duration_sec = float(manifest.get('duration') or metadata.get('conversion', {}).get('duration') or 0.0)
                episode.frame_count = int(manifest.get('frame_count') or metadata.get('conversion', {}).get('frame_count') or 0)
                episode.source_path = str(episode_dir)
                episode.source_hash = source_hash
                episode.ingest_status = 'indexed'
                episode.updated_at = datetime.utcnow()
            imported += 1

        job.progress = round(index * 100 / total)
        job.episodes = total
        job.imported_episodes = imported
        job.skipped_episodes = skipped
        job.detail = f'已扫描 {index}/{total}'

    batch.episode_count = db.query(Episode).filter(Episode.batch_id == batch.id).count()
    sync_batch_metrics(db, batch)
    _refresh_task_type_totals(db, task_type)

    job.status = 'indexed'
    job.progress = 100
    job.episodes = total
    job.imported_episodes = imported
    job.skipped_episodes = skipped
    job.detail = f'导入 {imported} 条，跳过 {skipped} 条'
    job.finished_at = datetime.utcnow()

    db.add(AuditEvent(
        id=f'audit_ingest_{job.id}',
        operator=operator.name,
        action='扫描入库',
        target=batch.id,
        detail=f'{source_root} imported={imported} skipped={skipped}',
        time=datetime.utcnow(),
    ))
    db.commit()
    db.refresh(job)
    return job
