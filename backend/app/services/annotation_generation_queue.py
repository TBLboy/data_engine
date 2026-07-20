"""Persistent annotation generation queue — mirror scan_queue pattern."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.models import AnnotationGenerationJob, AnnotationTask


ACTIVE_JOB_STATUSES = ('queued', 'running')
TERMINAL_JOB_STATUSES = ('succeeded', 'failed', 'cancelled', 'superseded', 'timeout')
MUTATING_JOB_TYPES = {'initial', 'all', 'instruction', 'variants', 'sub_goals'}
RETRY_DELAYS_SECONDS = (30, 120, 600)
GLOBAL_CONCURRENCY_LIMIT = 1


def _utcnow() -> datetime:
    return datetime.utcnow()


def create_generation_job(
    db: Session,
    *,
    annotation_task_id: str,
    job_type: str,
    task_description_snapshot: str,
    sub_goal_schema_id: str,
    sub_goal_schema_version: int,
    sub_goal_schema_content_hash: str,
    request_group_id: str | None = None,
    requested_draft_version: int | None = None,
    priority: int = 100,
    requested_by: str | None = None,
    next_retry_at: datetime | None = None,
) -> AnnotationGenerationJob:
    if job_type not in {'initial', 'all', 'instruction', 'variants', 'sub_goals', 'check'}:
        raise ValueError(f'未知 generation job type: {job_type}')

    if job_type in MUTATING_JOB_TYPES:
        existing = db.query(AnnotationGenerationJob).filter(
            AnnotationGenerationJob.annotation_task_id == annotation_task_id,
            AnnotationGenerationJob.job_type.in_(MUTATING_JOB_TYPES),
            AnnotationGenerationJob.status.in_(ACTIVE_JOB_STATUSES),
        ).first()
        if existing is not None:
            return existing

    now = _utcnow()
    job = AnnotationGenerationJob(
        annotation_task_id=annotation_task_id,
        request_group_id=request_group_id,
        job_type=job_type,
        status='queued',
        requested_draft_version=requested_draft_version,
        task_description_snapshot=task_description_snapshot,
        sub_goal_schema_id=sub_goal_schema_id,
        sub_goal_schema_version=sub_goal_schema_version,
        sub_goal_schema_content_hash=sub_goal_schema_content_hash,
        priority=priority,
        attempt_count=0,
        max_attempts=3,
        requested_by=requested_by,
        next_retry_at=next_retry_at,
        created_at=now,
    )
    db.add(job)
    db.flush()
    return job


def claim_next_job(db: Session, *, worker_id: str, lease_seconds: int) -> AnnotationGenerationJob | None:
    now = _utcnow()
    running_count = db.query(AnnotationGenerationJob).filter(
        AnnotationGenerationJob.status == 'running',
    ).count()
    if running_count >= GLOBAL_CONCURRENCY_LIMIT:
        return None

    query = db.query(AnnotationGenerationJob).filter(
        AnnotationGenerationJob.status.in_(('queued',)),
        AnnotationGenerationJob.cancel_requested_at.is_(None),
        or_(
            AnnotationGenerationJob.next_retry_at.is_(None),
            AnnotationGenerationJob.next_retry_at <= now,
        ),
    ).order_by(AnnotationGenerationJob.priority.asc(), AnnotationGenerationJob.id.asc())

    if db.get_bind().dialect.name == 'postgresql':
        query = query.with_for_update(skip_locked=True, of=AnnotationGenerationJob)
    else:
        query = query.with_for_update()
    job = query.first()
    if job is None:
        return None

    job.status = 'running'
    job.attempt_count += 1
    job.lease_owner = worker_id
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.next_retry_at = None
    job.started_at = job.started_at or now
    job.finished_at = None
    job.error_detail = ''
    db.flush()
    return job


def heartbeat_job(db: Session, *, job_id: str, worker_id: str, lease_seconds: int) -> bool:
    now = _utcnow()
    result = db.execute(
        update(AnnotationGenerationJob).where(
            AnnotationGenerationJob.id == job_id,
            AnnotationGenerationJob.status == 'running',
            AnnotationGenerationJob.lease_owner == worker_id,
        ).values(
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
    )
    return bool(result.rowcount)


def should_cancel_job(db: Session, *, job_id: str, worker_id: str) -> bool:
    row = db.query(AnnotationGenerationJob.cancel_requested_at, AnnotationGenerationJob.status,
                   AnnotationGenerationJob.lease_owner).filter(
        AnnotationGenerationJob.id == job_id,
    ).first()
    if row is None:
        return True
    return row.cancel_requested_at is not None or row.status != 'running' or row.lease_owner != worker_id


def complete_job(db: Session, *, job_id: str, worker_id: str) -> bool:
    now = _utcnow()
    result = db.execute(
        update(AnnotationGenerationJob).where(
            AnnotationGenerationJob.id == job_id,
            AnnotationGenerationJob.status == 'running',
            AnnotationGenerationJob.lease_owner == worker_id,
        ).values(
            status='succeeded',
            lease_owner='',
            lease_expires_at=None,
            heartbeat_at=now,
            error_detail='',
            finished_at=now,
        )
    )
    return bool(result.rowcount)


def fail_job(db: Session, *, job_id: str, worker_id: str, error: str, timed_out: bool = False) -> str | None:
    job = db.query(AnnotationGenerationJob).filter(
        AnnotationGenerationJob.id == job_id,
        AnnotationGenerationJob.status == 'running',
        AnnotationGenerationJob.lease_owner == worker_id,
    ).with_for_update().first()
    if job is None:
        return None
    now = _utcnow()
    job.error_detail = error[:4000]
    job.lease_owner = ''
    job.lease_expires_at = None
    job.heartbeat_at = now
    if job.cancel_requested_at is not None:
        job.status = 'cancelled'
        job.next_retry_at = None
        job.finished_at = now
    elif job.attempt_count < job.max_attempts:
        delay = RETRY_DELAYS_SECONDS[min(job.attempt_count - 1, len(RETRY_DELAYS_SECONDS) - 1)]
        jitter = int(hashlib.sha1(f'{job.id}:{job.attempt_count}'.encode()).hexdigest()[:2], 16) % 11
        job.status = 'queued'
        job.next_retry_at = now + timedelta(seconds=delay + jitter)
        job.finished_at = None
    else:
        job.status = 'timeout' if timed_out else 'failed'
        job.next_retry_at = None
        job.finished_at = now
    db.flush()
    return job.status


def cancel_pending_jobs_for_task(db: Session, *, annotation_task_id: str) -> int:
    """Cancel queued jobs immediately; request cancel for running jobs."""
    now = _utcnow()
    queued = db.execute(
        update(AnnotationGenerationJob).where(
            AnnotationGenerationJob.annotation_task_id == annotation_task_id,
            AnnotationGenerationJob.status == 'queued',
        ).values(
            status='cancelled',
            cancel_requested_at=now,
            finished_at=now,
            error_detail='task invalidated or scope changed',
        )
    )
    running = db.execute(
        update(AnnotationGenerationJob).where(
            AnnotationGenerationJob.annotation_task_id == annotation_task_id,
            AnnotationGenerationJob.status == 'running',
        ).values(
            cancel_requested_at=now,
            error_detail='task invalidated or scope changed; cancel requested',
        )
    )
    return int(queued.rowcount or 0) + int(running.rowcount or 0)


def request_cancel_job(db: Session, *, job_id: str) -> AnnotationGenerationJob | None:
    job = db.query(AnnotationGenerationJob).filter(
        AnnotationGenerationJob.id == job_id,
    ).with_for_update().first()
    if job is None:
        return None
    if job.status in TERMINAL_JOB_STATUSES:
        return job
    now = _utcnow()
    job.cancel_requested_at = now
    job.error_detail = 'cancelling by request'
    if job.status == 'queued':
        job.status = 'cancelled'
        job.finished_at = now
        job.lease_owner = ''
        job.lease_expires_at = None
    db.flush()
    return job


def retry_failed_job(db: Session, *, job_id: str, requested_by: str | None = None) -> AnnotationGenerationJob | None:
    """Re-queue a terminal failed/timeout job as a new attempt cycle."""
    job = db.query(AnnotationGenerationJob).filter(
        AnnotationGenerationJob.id == job_id,
    ).with_for_update().first()
    if job is None:
        return None
    if job.status not in {'failed', 'timeout', 'cancelled'}:
        return job
    now = _utcnow()
    job.status = 'queued'
    job.attempt_count = 0
    job.next_retry_at = None
    job.cancel_requested_at = None
    job.error_detail = ''
    job.lease_owner = ''
    job.lease_expires_at = None
    job.heartbeat_at = None
    job.started_at = None
    job.finished_at = None
    if requested_by:
        job.requested_by = requested_by
    job.created_at = job.created_at or now
    db.flush()
    return job


def reclaim_expired_leases(db: Session, *, lease_seconds: int) -> int:
    now = _utcnow()
    expired = db.query(AnnotationGenerationJob).filter(
        AnnotationGenerationJob.status == 'running',
        AnnotationGenerationJob.lease_expires_at.is_not(None),
        AnnotationGenerationJob.lease_expires_at <= now,
    ).all()
    for job in expired:
        job.status = 'queued'
        job.next_retry_at = now
        job.lease_owner = ''
        job.lease_expires_at = None
        job.error_detail = f'lease expired; recovered by coordinator at {now.isoformat()}'
    db.flush()
    return len(expired)
