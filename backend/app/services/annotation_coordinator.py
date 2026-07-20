"""Annotation generation coordinator — periodic discovery and lease reclamation."""

from __future__ import annotations

import logging
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import AnnotationGenerationJob, AnnotationTask, Batch, Episode, SubGoalSchema, TaskType
from app.services.annotation import active_qualified_episode_query, ensure_task_for_episode
from app.services.annotation_generation_queue import (
    create_generation_job,
    reclaim_expired_leases,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _parse_hhmm(value: str, *, default: dt_time) -> dt_time:
    text = (value or '').strip()
    if not text:
        return default
    try:
        hour_s, minute_s = text.split(':', 1)
        hour = int(hour_s)
        minute = int(minute_s)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return default
        return dt_time(hour=hour, minute=minute)
    except Exception:
        return default


def discovery_local_now(settings=None) -> datetime:
    settings = settings or get_settings()
    try:
        tz = ZoneInfo(settings.annotation_discovery_timezone or 'Asia/Shanghai')
    except Exception:
        tz = ZoneInfo('Asia/Shanghai')
    return datetime.now(tz)


def is_discovery_window_open(now: datetime | None = None, settings=None) -> bool:
    """Return True when auto discovery may enqueue new initial jobs.

    Window is local wall-clock [start, end). Equal start/end means always open.
    Overnight windows are supported (e.g. 22:00-06:00).
    Manual enqueue is never gated by this helper.
    """
    settings = settings or get_settings()
    if not settings.annotation_discovery_enabled:
        return False
    current = now or discovery_local_now(settings)
    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo('UTC'))
    start = _parse_hhmm(settings.annotation_discovery_window_start, default=dt_time(0, 0))
    end = _parse_hhmm(settings.annotation_discovery_window_end, default=dt_time(6, 0))
    local_t = current.timetz().replace(tzinfo=None)
    if start == end:
        return True
    if start < end:
        return start <= local_t < end
    # Overnight: open if >= start OR < end
    return local_t >= start or local_t < end


def _local_day_bounds_utc(now: datetime | None = None, settings=None) -> tuple[datetime, datetime]:
    """Return [local_midnight, next_local_midnight) as naive UTC datetimes for DB compare."""
    settings = settings or get_settings()
    current = now or discovery_local_now(settings)
    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo(settings.annotation_discovery_timezone or 'Asia/Shanghai'))
    local_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    start_utc = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = local_end.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


def count_auto_initial_jobs_today(db: Session, *, now: datetime | None = None, settings=None) -> int:
    settings = settings or get_settings()
    start_utc, end_utc = _local_day_bounds_utc(now, settings)
    return int(
        db.query(func.count(AnnotationGenerationJob.id))
        .filter(
            AnnotationGenerationJob.job_type == 'initial',
            AnnotationGenerationJob.request_group_id.like('auto-%'),
            AnnotationGenerationJob.created_at >= start_utc,
            AnnotationGenerationJob.created_at < end_utc,
        )
        .scalar()
        or 0
    )


def remaining_discovery_quota(db: Session, *, now: datetime | None = None, settings=None) -> int | None:
    """None = unlimited; otherwise remaining auto jobs allowed today."""
    settings = settings or get_settings()
    limit = int(settings.annotation_discovery_daily_limit or 0)
    if limit <= 0:
        return None
    used = count_auto_initial_jobs_today(db, now=now, settings=settings)
    return max(0, limit - used)


def _existing_initial_job(db: Session, annotation_task_id: str) -> AnnotationGenerationJob | None:
    """Return active or succeeded initial job (idempotent re-enqueue target)."""
    return (
        db.query(AnnotationGenerationJob)
        .filter(
            AnnotationGenerationJob.annotation_task_id == annotation_task_id,
            AnnotationGenerationJob.job_type == 'initial',
            AnnotationGenerationJob.status.in_(('queued', 'running', 'succeeded')),
        )
        .order_by(AnnotationGenerationJob.id.asc())
        .first()
    )


def _task_description_for_task(db: Session, task: AnnotationTask) -> str:
    batch = db.query(Batch).filter(Batch.id == task.batch_id).first()
    if batch and batch.task_type and batch.task_type.description:
        return batch.task_type.description
    task_type = db.query(TaskType).filter(TaskType.id == task.task_type_id).first()
    return task_type.description if task_type else ''


def enqueue_initial_job_for_task(
    db: Session,
    task: AnnotationTask,
    *,
    request_group_id: str | None = None,
    requested_by: str | None = None,
    priority: int = 100,
) -> AnnotationGenerationJob | None:
    """Create or return existing initial generation job (idempotent)."""
    if task.work_status == 'invalidated':
        return None
    if task.work_status not in {'pending', 'assigned', 'in_progress'}:
        return None
    existing = _existing_initial_job(db, task.id)
    if existing is not None:
        return existing
    return create_generation_job(
        db,
        annotation_task_id=task.id,
        job_type='initial',
        task_description_snapshot=_task_description_for_task(db, task),
        sub_goal_schema_id=task.sub_goal_schema_id,
        sub_goal_schema_version=task.sub_goal_schema_version,
        sub_goal_schema_content_hash=task.sub_goal_schema_content_hash,
        request_group_id=request_group_id,
        requested_by=requested_by,
        priority=priority,
    )


def discover_eligible_tasks(
    db: Session,
    *,
    limit: int = 50,
    now: datetime | None = None,
    settings=None,
) -> int:
    """Idempotently create annotation tasks + initial VLM jobs for eligible episodes.

    Respects deploy night window + daily auto quota. Manual enqueue bypasses this gate.
    """
    settings = settings or get_settings()
    if not is_discovery_window_open(now=now, settings=settings):
        logger.info('auto discovery skipped: outside configured window or disabled')
        return 0
    remaining = remaining_discovery_quota(db, now=now, settings=settings)
    if remaining is not None:
        if remaining <= 0:
            logger.info('auto discovery skipped: daily limit reached')
            return 0
        limit = min(limit, remaining)

    request_group_id = f'auto-{_utcnow().strftime("%Y%m%d-%H%M%S")}'
    created = 0

    # Path 1: active QUALIFIED episodes with no annotation task yet.
    episodes_without_task = (
        active_qualified_episode_query(db)
        .outerjoin(AnnotationTask, AnnotationTask.episode_id == Episode.id)
        .filter(AnnotationTask.id.is_(None))
        .order_by(Episode.id.asc())
        .limit(limit)
        .all()
    )
    for episode in episodes_without_task:
        batch = db.query(Batch).filter(Batch.id == episode.batch_id).first()
        if not batch or not batch.task_type_id:
            continue
        schema_id = (
            db.query(TaskType.default_published_sub_goal_schema_id)
            .filter(TaskType.id == batch.task_type_id)
            .scalar()
        )
        if not schema_id:
            continue
        schema = (
            db.query(SubGoalSchema)
            .filter(
                SubGoalSchema.id == schema_id,
                SubGoalSchema.task_type_id == batch.task_type_id,
                SubGoalSchema.status == 'published',
            )
            .first()
        )
        if not schema:
            continue
        task = ensure_task_for_episode(db, episode, initial_source='vlm')
        job = enqueue_initial_job_for_task(
            db,
            task,
            request_group_id=request_group_id,
            priority=100,
        )
        # Newly created jobs carry this pass's request_group_id.
        if job is not None and job.request_group_id == request_group_id:
            created += 1
        if created >= limit:
            return created

    remaining = max(0, limit - created)
    if remaining <= 0:
        return created

    # Path 2: existing active tasks that still lack an active/succeeded initial job.
    active_initial = exists().where(
        and_(
            AnnotationGenerationJob.annotation_task_id == AnnotationTask.id,
            AnnotationGenerationJob.job_type == 'initial',
            AnnotationGenerationJob.status.in_(('queued', 'running', 'succeeded')),
        )
    )
    tasks = (
        db.query(AnnotationTask)
        .filter(
            AnnotationTask.work_status.in_(('pending', 'assigned', 'in_progress')),
            ~active_initial,
        )
        .order_by(AnnotationTask.id.asc())
        .limit(remaining)
        .all()
    )
    for task in tasks:
        # Only enqueue when episode is still in active QUALIFIED scope.
        episode = (
            active_qualified_episode_query(db)
            .filter(Episode.id == task.episode_id)
            .first()
        )
        if episode is None:
            continue
        job = enqueue_initial_job_for_task(
            db,
            task,
            request_group_id=request_group_id,
            priority=100,
        )
        if job is not None and job.request_group_id == request_group_id:
            created += 1
    return created


def run_coordinator_forever() -> None:
    settings = get_settings()
    logger.info('annotation coordinator started')
    while True:
        db = SessionLocal()
        try:
            reclaimed = reclaim_expired_leases(db, lease_seconds=settings.annotation_worker_lease_seconds)
            if reclaimed:
                db.commit()
                logger.info('reclaimed %d expired generation job leases', reclaimed)
            else:
                db.rollback()
        except Exception:
            db.rollback()
            logger.exception('coordinator lease reclamation failed')
        finally:
            db.close()

        db = SessionLocal()
        try:
            # Lease reclaim always runs; discovery only inside night window + daily quota.
            discovered = discover_eligible_tasks(db, limit=50)
            if discovered:
                db.commit()
                logger.info('discovered %d eligible episodes for initial VLM annotation', discovered)
            else:
                db.rollback()
        except Exception:
            db.rollback()
            logger.exception('coordinator discovery failed')
        finally:
            db.close()
        time.sleep(max(1.0, settings.annotation_coordinator_interval_seconds))


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_coordinator_forever()


if __name__ == '__main__':
    main()
