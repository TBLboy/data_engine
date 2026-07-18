from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ScanJob, ScanShard


ACTIVE_JOB_STATUSES = ('queued', 'discovering', 'running', 'cancelling')
ACTIVE_SHARD_STATUSES = ('pending', 'running', 'retry_wait')
TERMINAL_SHARD_STATUSES = ('succeeded', 'skipped', 'failed', 'cancelled', 'timeout')
RETRY_DELAYS_SECONDS = (30, 120, 600)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _job_id() -> str:
    return f'scan_{uuid.uuid4().hex}'


def _active_key(bucket: str) -> str:
    return f'scan:{bucket}'


def _shard_key(shard_type: str, prefix: str, suffix: str = '') -> str:
    value = f'{shard_type}:{prefix}'
    if suffix:
        value = f'{value}:{suffix}'
    if len(value) <= 1200:
        return value
    digest = hashlib.sha1(value.encode('utf-8')).hexdigest()
    return f'{value[:1158]}:{digest}'


def add_scan_shard(
    db: Session,
    *,
    job: ScanJob,
    shard_type: str,
    prefix: str = '',
    priority: int | None = None,
    next_retry_at: datetime | None = None,
    suffix: str = '',
    parent_shard_id: int | None = None,
    range_start: str = '',
    range_end: str = '',
) -> ScanShard:
    key = _shard_key(shard_type, prefix, suffix)
    existing = db.query(ScanShard).filter(
        ScanShard.scan_job_id == job.id,
        ScanShard.shard_key == key,
    ).first()
    if existing is not None:
        return existing
    shard = ScanShard(
        scan_job_id=job.id,
        parent_shard_id=parent_shard_id,
        shard_key=key,
        shard_type=shard_type,
        bucket=job.bucket,
        prefix=prefix,
        range_start=range_start,
        range_end=range_end,
        status='retry_wait' if next_retry_at else 'pending',
        priority=priority if priority is not None else job.priority,
        attempt=0,
        max_attempts=3,
        lease_owner='',
        timeout_seconds=600,
        next_retry_at=next_retry_at,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(shard)
    db.flush()
    return shard


def create_or_get_scan_job(
    db: Session,
    *,
    bucket: str,
    mode: str,
    triggered_by: str,
    trigger_source: str = 'manual',
    priority: int = 100,
    prefixes: list[str] | None = None,
    job_id: str | None = None,
) -> tuple[ScanJob, bool]:
    normalized_bucket = bucket.strip()
    normalized_mode = mode.strip().lower()
    if not normalized_bucket:
        raise ValueError('bucket cannot be empty')
    if normalized_mode not in {'smart', 'incremental', 'full', 'manual_prefix'}:
        raise ValueError(f'unsupported scan mode: {mode}')
    normalized_prefixes = sorted({f'{item.strip("/")}/' for item in prefixes or [] if item.strip('/')})
    if normalized_mode == 'manual_prefix' and not normalized_prefixes:
        raise ValueError('manual_prefix requires at least one prefix')
    if normalized_mode == 'smart':
        recent_full = db.query(ScanJob.id).filter(
            ScanJob.bucket == normalized_bucket,
            ScanJob.scan_mode == 'full',
            ScanJob.status == 'succeeded',
            ScanJob.finished_at >= _utcnow() - timedelta(days=7),
        ).first()
        if recent_full is None:
            normalized_mode = 'full'

    active = db.query(ScanJob).filter(
        ScanJob.bucket == normalized_bucket,
        ScanJob.status.in_(ACTIVE_JOB_STATUSES),
    ).order_by(ScanJob.created_at.desc()).first()
    if active is not None:
        return active, False

    now = _utcnow()
    job = ScanJob(
        id=job_id or _job_id(),
        bucket=normalized_bucket,
        scope=normalized_mode,
        status='queued',
        total_prefixes=0,
        confirmed_lists=0,
        total_episodes=0,
        new_episodes=0,
        triggered_by=triggered_by,
        error_detail='queued',
        started_at=now,
        finished_at=None,
        scan_mode=normalized_mode,
        priority=priority,
        trigger_source=trigger_source,
        active_key=_active_key(normalized_bucket),
        heartbeat_at=now,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        if job_id is not None:
            existing = db.query(ScanJob).filter(ScanJob.id == job_id).first()
            if existing is not None:
                return existing, False
        active = db.query(ScanJob).filter(ScanJob.active_key == _active_key(normalized_bucket)).first()
        if active is None:
            raise
        return active, False

    if normalized_mode == 'manual_prefix':
        for prefix in normalized_prefixes:
            add_scan_shard(db, job=job, shard_type='list', prefix=prefix)
    else:
        add_scan_shard(db, job=job, shard_type='namespace_discovery', prefix='')
    job.total_shards = len(normalized_prefixes) if normalized_mode == 'manual_prefix' else 1
    job.status = 'queued'
    job.error_detail = f'shards={job.total_shards} queued'
    return job, True


def claim_next_shard(db: Session, *, worker_id: str, lease_seconds: int) -> ScanShard | None:
    now = _utcnow()
    query = db.query(ScanShard).join(ScanJob, ScanShard.scan_job_id == ScanJob.id).filter(
        ScanJob.status.in_(('queued', 'discovering', 'running')),
        ScanJob.cancel_requested_at.is_(None),
        or_(
            ScanShard.status == 'pending',
            (ScanShard.status == 'retry_wait') & (ScanShard.next_retry_at <= now),
        ),
    ).order_by(ScanShard.priority.asc(), ScanShard.id.asc())
    if db.get_bind().dialect.name == 'postgresql':
        query = query.with_for_update(skip_locked=True, of=ScanShard)
    else:
        query = query.with_for_update()
    shard = query.first()
    if shard is None:
        return None
    shard.status = 'running'
    shard.attempt += 1
    shard.lease_owner = worker_id
    shard.heartbeat_at = now
    shard.lease_expires_at = now + timedelta(seconds=lease_seconds)
    shard.next_retry_at = None
    shard.started_at = shard.started_at or now
    shard.finished_at = None
    shard.error_detail = ''
    shard.updated_at = now
    job = db.query(ScanJob).filter(ScanJob.id == shard.scan_job_id).first()
    if job is not None:
        job.status = 'discovering' if shard.shard_type == 'namespace_discovery' else 'running'
        job.heartbeat_at = now
        job.updated_at = now
    db.flush()
    return shard


def heartbeat_shard(
    db: Session,
    *,
    shard_id: int,
    worker_id: str,
    lease_seconds: int,
) -> bool:
    now = _utcnow()
    result = db.execute(
        update(ScanShard).where(
            ScanShard.id == shard_id,
            ScanShard.status == 'running',
            ScanShard.lease_owner == worker_id,
        ).values(
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            updated_at=now,
        )
    )
    return bool(result.rowcount)


def should_cancel_shard(db: Session, *, shard_id: int, worker_id: str) -> bool:
    row = db.query(ScanJob.cancel_requested_at, ScanShard.status, ScanShard.lease_owner).join(
        ScanShard, ScanShard.scan_job_id == ScanJob.id
    ).filter(ScanShard.id == shard_id).first()
    if row is None:
        return True
    return row.cancel_requested_at is not None or row.status != 'running' or row.lease_owner != worker_id


def complete_shard(
    db: Session,
    *,
    shard_id: int,
    worker_id: str,
    processed_objects: int = 0,
    processed_episodes: int = 0,
    changed_episodes: int = 0,
    new_episodes: int = 0,
) -> bool:
    now = _utcnow()
    result = db.execute(
        update(ScanShard).where(
            ScanShard.id == shard_id,
            ScanShard.status == 'running',
            ScanShard.lease_owner == worker_id,
        ).values(
            status='succeeded',
            processed_objects=processed_objects,
            total_objects=processed_objects,
            processed_episodes=processed_episodes,
            total_episodes=processed_episodes,
            changed_episodes=changed_episodes,
            new_episodes=new_episodes,
            lease_owner='',
            lease_expires_at=None,
            heartbeat_at=now,
            error_detail='',
            finished_at=now,
            updated_at=now,
        )
    )
    return bool(result.rowcount)


def cancel_running_shard(db: Session, *, shard_id: int, worker_id: str) -> bool:
    now = _utcnow()
    result = db.execute(
        update(ScanShard).where(
            ScanShard.id == shard_id,
            ScanShard.status == 'running',
            ScanShard.lease_owner == worker_id,
        ).values(
            status='cancelled',
            lease_owner='',
            lease_expires_at=None,
            error_detail='cancelled by request',
            finished_at=now,
            updated_at=now,
        )
    )
    return bool(result.rowcount)


def fail_shard(
    db: Session,
    *,
    shard_id: int,
    worker_id: str,
    error: str,
    timed_out: bool = False,
) -> str | None:
    shard = db.query(ScanShard).filter(
        ScanShard.id == shard_id,
        ScanShard.status == 'running',
        ScanShard.lease_owner == worker_id,
    ).with_for_update().first()
    if shard is None:
        return None
    now = _utcnow()
    shard.error_detail = error[:4000]
    shard.lease_owner = ''
    shard.lease_expires_at = None
    shard.heartbeat_at = now
    shard.updated_at = now
    if shard.attempt < shard.max_attempts:
        delay = RETRY_DELAYS_SECONDS[min(shard.attempt - 1, len(RETRY_DELAYS_SECONDS) - 1)]
        jitter = int(hashlib.sha1(f'{shard.id}:{shard.attempt}'.encode()).hexdigest()[:2], 16) % 11
        shard.status = 'retry_wait'
        shard.next_retry_at = now + timedelta(seconds=delay + jitter)
        shard.finished_at = None
    else:
        shard.status = 'timeout' if timed_out else 'failed'
        shard.next_retry_at = None
        shard.finished_at = now
    db.flush()
    return shard.status


def request_cancel(db: Session, *, job_id: str) -> ScanJob | None:
    job = db.query(ScanJob).filter(ScanJob.id == job_id).with_for_update().first()
    if job is None:
        return None
    if job.status not in ACTIVE_JOB_STATUSES:
        return job
    now = _utcnow()
    job.cancel_requested_at = now
    job.status = 'cancelling'
    job.updated_at = now
    db.query(ScanShard).filter(
        ScanShard.scan_job_id == job.id,
        ScanShard.status.in_(('pending', 'retry_wait')),
    ).update({
        ScanShard.status: 'cancelled',
        ScanShard.finished_at: now,
        ScanShard.updated_at: now,
        ScanShard.error_detail: 'cancelled before execution',
    }, synchronize_session=False)
    return job


def retry_failed_shards(db: Session, *, job_id: str) -> tuple[ScanJob | None, int]:
    job = db.query(ScanJob).filter(ScanJob.id == job_id).with_for_update().first()
    if job is None:
        return None, 0
    other_active = db.query(ScanJob.id).filter(
        ScanJob.bucket == job.bucket,
        ScanJob.id != job.id,
        ScanJob.status.in_(ACTIVE_JOB_STATUSES),
    ).first()
    if other_active is not None:
        raise ValueError('another scan job is active for this bucket')
    now = _utcnow()
    count = db.query(ScanShard).filter(
        ScanShard.scan_job_id == job.id,
        ScanShard.status.in_(('failed', 'timeout')),
    ).update({
        ScanShard.status: 'pending',
        ScanShard.attempt: 0,
        ScanShard.next_retry_at: None,
        ScanShard.error_detail: '',
        ScanShard.finished_at: None,
        ScanShard.updated_at: now,
    }, synchronize_session=False)
    if count:
        job.status = 'queued'
        job.active_key = _active_key(job.bucket)
        job.cancel_requested_at = None
        job.finished_at = None
        job.error_summary = ''
        job.error_detail = f'retrying {count} failed shards'
        job.updated_at = now
    return job, count


def enqueue_scan_job(scan_job_id: str, operator_id: str) -> None:
    """Compatibility no-op: v3 workers poll PostgreSQL instead of starting threads."""
    del scan_job_id, operator_id
