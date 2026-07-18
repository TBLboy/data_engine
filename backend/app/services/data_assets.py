from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import BIGINT, case, cast, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    Batch,
    BatchAssetRecomputeJob,
    BatchAssetRollup,
    Episode,
    ListRecord,
    TaskAssetRecomputeJob,
    TaskAssetRollup,
    TaskType,
)


ROLLUP_VERSION = 'batch-asset-rollup-v1'
TASK_ROLLUP_VERSION = 'task-asset-rollup-v1'
RECOMPUTE_REASONS = {
    'scan_sync',
    'episode_qc_changed',
    'dispatch_changed',
    'batch_relation_changed',
    'list_scope_changed',
    'manual_rebuild',
    'task_relation_changed',
    'child_batch_refreshed',
}


def _utcnow() -> datetime:
    return datetime.utcnow()


def _find_pending_instance(db: Session, model_type: type, identity_key: str, identity_value: str):
    """Locate an unflushed or dirty instance already tracked by the session."""
    for collection in (db.new, db.dirty, db.identity_map.values()):
        for obj in collection:
            if isinstance(obj, model_type) and getattr(obj, identity_key, None) == identity_value:
                return obj
    return None


def _query_or_pending(db: Session, model_type: type, identity_key: str, identity_value: str):
    """SQLite-safe lookup that sees both flushed rows and pending session objects."""
    pending = _find_pending_instance(db, model_type, identity_key, identity_value)
    if pending is not None:
        return pending
    db.flush()
    return db.query(model_type).filter(getattr(model_type, identity_key) == identity_value).first()


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return float(numerator) / float(denominator)


def active_batch_query(db: Session):
    return db.query(Batch).join(ListRecord, Batch.list_id == ListRecord.id).filter(
        Batch.is_active == True,
        Batch.list_id.is_not(None),
        ListRecord.is_active == True,
    )


def active_episode_query(db: Session):
    return db.query(Episode).join(Batch, Episode.batch_id == Batch.id).join(ListRecord, Batch.list_id == ListRecord.id).filter(
        Batch.is_active == True,
        Batch.list_id.is_not(None),
        ListRecord.is_active == True,
        Episode.is_active == True,
    )


def enqueue_batch_asset_recompute(db: Session, batch_id: str, *, reason: str) -> None:
    normalized_reason = reason if reason in RECOMPUTE_REASONS else 'manual_rebuild'
    now = _utcnow()
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == 'postgresql':
        stmt = insert(BatchAssetRecomputeJob).values(
            batch_id=batch_id,
            reason=normalized_reason,
            requested_at=now,
            status='pending',
            attempts=0,
            last_error='',
            last_started_at=None,
            last_finished_at=None,
            rerun_requested=False,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[BatchAssetRecomputeJob.batch_id],
            set_={
                'reason': normalized_reason,
                'requested_at': now,
                'status': case(
                    (BatchAssetRecomputeJob.status == 'running', 'running'),
                    else_='pending',
                ),
                'rerun_requested': case(
                    (BatchAssetRecomputeJob.status == 'running', True),
                    else_=False,
                ),
                'last_error': case(
                    (BatchAssetRecomputeJob.status == 'running', BatchAssetRecomputeJob.last_error),
                    else_='',
                ),
            },
        )
        db.execute(stmt)
        return

    job = _query_or_pending(db, BatchAssetRecomputeJob, 'batch_id', batch_id)
    if job:
        job.reason = normalized_reason
        job.requested_at = now
        if job.status == 'running':
            job.rerun_requested = True
        else:
            job.status = 'pending'
            job.rerun_requested = False
            job.last_error = ''
        return
    db.add(
        BatchAssetRecomputeJob(
            batch_id=batch_id,
            reason=normalized_reason,
            requested_at=now,
            status='pending',
            attempts=0,
            last_error='',
            last_started_at=None,
            last_finished_at=None,
            rerun_requested=False,
        )
    )


def enqueue_list_scope_recompute(db: Session, list_id: str, *, reason: str) -> int:
    batch_ids = [item.id for item in db.query(Batch.id).filter(Batch.list_id == list_id).all()]
    for batch_id in batch_ids:
        enqueue_batch_asset_recompute(db, batch_id, reason=reason)
    return len(batch_ids)


def enqueue_task_asset_recompute(db: Session, task_type_id: str, *, reason: str) -> None:
    if not task_type_id:
        return
    normalized_reason = reason if reason in RECOMPUTE_REASONS else 'manual_rebuild'
    now = _utcnow()
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == 'postgresql':
        stmt = insert(TaskAssetRecomputeJob).values(
            task_type_id=task_type_id,
            reason=normalized_reason,
            requested_at=now,
            status='pending',
            attempts=0,
            last_error='',
            last_started_at=None,
            last_finished_at=None,
            rerun_requested=False,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[TaskAssetRecomputeJob.task_type_id],
            set_={
                'reason': normalized_reason,
                'requested_at': now,
                'status': case(
                    (TaskAssetRecomputeJob.status == 'running', 'running'),
                    else_='pending',
                ),
                'rerun_requested': case(
                    (TaskAssetRecomputeJob.status == 'running', True),
                    else_=False,
                ),
                'last_error': case(
                    (TaskAssetRecomputeJob.status == 'running', TaskAssetRecomputeJob.last_error),
                    else_='',
                ),
            },
        )
        db.execute(stmt)
        return

    job = _query_or_pending(db, TaskAssetRecomputeJob, 'task_type_id', task_type_id)
    if job:
        job.reason = normalized_reason
        job.requested_at = now
        if job.status == 'running':
            job.rerun_requested = True
        else:
            job.status = 'pending'
            job.rerun_requested = False
            job.last_error = ''
        return
    db.add(
        TaskAssetRecomputeJob(
            task_type_id=task_type_id,
            reason=normalized_reason,
            requested_at=now,
            status='pending',
            attempts=0,
            last_error='',
            last_started_at=None,
            last_finished_at=None,
            rerun_requested=False,
        )
    )


def enqueue_task_assets_for_batches(db: Session, *batch_ids: str, reason: str = 'child_batch_refreshed') -> int:
    unique_batch_ids = {batch_id for batch_id in batch_ids if batch_id}
    if not unique_batch_ids:
        return 0
    task_type_ids = [
        item.task_type_id
        for item in db.query(Batch.task_type_id).filter(Batch.id.in_(unique_batch_ids)).distinct().all()
        if item.task_type_id
    ]
    for task_type_id in task_type_ids:
        enqueue_task_asset_recompute(db, task_type_id, reason=reason)
    return len(task_type_ids)


@dataclass(slots=True)
class BatchAssetSummary:
    episode_count: int
    batch_count: int
    task_type_count: int
    failure_reason_count: int
    total_duration_sec: float
    total_frame_count: int
    duration_covered_episode_count: int
    duration_missing_episode_count: int
    frame_covered_episode_count: int
    frame_missing_episode_count: int
    stale_batch_count: int
    oldest_refreshed_at: datetime | None
    newest_refreshed_at: datetime | None
    statistics_scope: str
    calculation_version: str


def recompute_batch_asset_rollup(db: Session, batch_id: str) -> BatchAssetRollup | None:
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        return None

    now = _utcnow()
    aggregate = db.query(
        func.count(Episode.id).label('episode_count'),
        func.coalesce(func.sum(case((Episode.duration_sec > 0, Episode.duration_sec), else_=0.0)), 0.0).label('total_duration_sec'),
        func.coalesce(func.sum(case((Episode.duration_sec > 0, 1), else_=0)), 0).label('duration_covered_episode_count'),
        func.coalesce(func.sum(case((Episode.duration_sec > 0, 0), else_=1)), 0).label('duration_missing_episode_count'),
        func.coalesce(func.sum(case((Episode.frame_count > 0, cast(Episode.frame_count, BIGINT)), else_=cast(0, BIGINT))), 0).label('total_frame_count'),
        func.coalesce(func.sum(case((Episode.frame_count > 0, 1), else_=0)), 0).label('frame_covered_episode_count'),
        func.coalesce(func.sum(case((Episode.frame_count > 0, 0), else_=1)), 0).label('frame_missing_episode_count'),
        func.coalesce(func.sum(case((Episode.sampled_for_qc == 1, 1), else_=0)), 0).label('sampled_episode_count'),
        func.coalesce(func.sum(case((Episode.manual_qc_status.in_(['MANUAL_PASS', 'MANUAL_FAIL']), 1), else_=0)), 0).label('reviewed_count'),
        func.coalesce(func.sum(case((Episode.manual_qc_status == 'MANUAL_PASS', 1), else_=0)), 0).label('manual_pass_count'),
        func.coalesce(func.sum(case((Episode.manual_qc_status == 'MANUAL_FAIL', 1), else_=0)), 0).label('manual_fail_count'),
        func.coalesce(func.sum(case((Episode.final_dataset_status == 'QUALIFIED', 1), else_=0)), 0).label('qualified_count'),
        func.coalesce(func.sum(case((Episode.final_dataset_status == 'UNQUALIFIED', 1), else_=0)), 0).label('unqualified_count'),
        func.coalesce(func.sum(case((Episode.final_dataset_status == 'PENDING', 1), else_=0)), 0).label('pending_dataset_count'),
        func.max(Episode.updated_at).label('last_episode_updated_at'),
    ).filter(Episode.batch_id == batch_id, Episode.is_active == True).one()

    source_updated_at = aggregate.last_episode_updated_at.isoformat() if aggregate.last_episode_updated_at else 'none'
    source_watermark = f'episodes:{aggregate.episode_count}:updated:{source_updated_at}'

    rollup = _query_or_pending(db, BatchAssetRollup, 'batch_id', batch_id)
    if not rollup:
        rollup = BatchAssetRollup(
            batch_id=batch_id,
            refreshed_at=now,
        )
        db.add(rollup)

    rollup.episode_count = int(aggregate.episode_count or 0)
    rollup.total_duration_sec = float(aggregate.total_duration_sec or 0.0)
    rollup.duration_covered_episode_count = int(aggregate.duration_covered_episode_count or 0)
    rollup.duration_missing_episode_count = int(aggregate.duration_missing_episode_count or 0)
    rollup.total_frame_count = int(aggregate.total_frame_count or 0)
    rollup.frame_covered_episode_count = int(aggregate.frame_covered_episode_count or 0)
    rollup.frame_missing_episode_count = int(aggregate.frame_missing_episode_count or 0)
    rollup.sampled_episode_count = int(aggregate.sampled_episode_count or 0)
    rollup.reviewed_count = int(aggregate.reviewed_count or 0)
    rollup.manual_pass_count = int(aggregate.manual_pass_count or 0)
    rollup.manual_fail_count = int(aggregate.manual_fail_count or 0)
    rollup.qualified_count = int(aggregate.qualified_count or 0)
    rollup.unqualified_count = int(aggregate.unqualified_count or 0)
    rollup.pending_dataset_count = int(aggregate.pending_dataset_count or 0)
    rollup.last_episode_updated_at = aggregate.last_episode_updated_at
    rollup.source_watermark = source_watermark
    rollup.calculation_version = ROLLUP_VERSION
    rollup.refreshed_at = now

    # Make the updated batch projection visible to subsequent task aggregation
    # within the same autoflush=False session.
    db.flush()
    job = _query_or_pending(db, BatchAssetRecomputeJob, 'batch_id', batch_id)
    if job:
        job.status = 'pending' if job.rerun_requested else 'done'
        job.rerun_requested = False
        job.attempts += 1
        job.last_error = ''
        job.last_started_at = job.last_started_at or now
        job.last_finished_at = now

    if batch.task_type_id:
        enqueue_task_asset_recompute(db, batch.task_type_id, reason='child_batch_refreshed')

    return rollup


def mark_recompute_started(db: Session, batch_id: str) -> BatchAssetRecomputeJob | None:
    job = db.query(BatchAssetRecomputeJob).filter(BatchAssetRecomputeJob.batch_id == batch_id).with_for_update().first()
    if not job:
        return None
    if job.status not in ('pending', 'failed'):
        return None
    job.status = 'running'
    job.rerun_requested = False
    job.last_started_at = _utcnow()
    job.last_error = ''
    return job


def mark_recompute_failed(db: Session, batch_id: str, *, error: str) -> None:
    job = db.query(BatchAssetRecomputeJob).filter(BatchAssetRecomputeJob.batch_id == batch_id).first()
    if not job:
        return
    job.status = 'failed'
    job.attempts += 1
    job.last_error = error[:500]
    job.last_finished_at = _utcnow()


def rebuild_all_active_batch_rollups(db: Session) -> int:
    batch_ids = [item.id for item in active_batch_query(db).all()]
    for batch_id in batch_ids:
        recompute_batch_asset_rollup(db, batch_id)
    return len(batch_ids)


def _task_has_pending_child_batch_jobs(db: Session, task_type_id: str) -> bool:
    pending_child = (
        active_batch_query(db)
        .join(BatchAssetRecomputeJob, BatchAssetRecomputeJob.batch_id == Batch.id)
        .filter(
            Batch.task_type_id == task_type_id,
            BatchAssetRecomputeJob.status.in_(['pending', 'running', 'failed']),
        )
        .first()
    )
    return pending_child is not None


def recompute_task_asset_rollup(db: Session, task_type_id: str) -> TaskAssetRollup | None:
    task_type = db.query(TaskType).filter(TaskType.id == task_type_id).first()
    if not task_type:
        return None

    # Ensure any just-written batch rollups/jobs are visible before decisions.
    db.flush()
    if _task_has_pending_child_batch_jobs(db, task_type_id):
        job = _query_or_pending(db, TaskAssetRecomputeJob, 'task_type_id', task_type_id)
        if job and job.status in ('pending', 'running', 'failed'):
            job.status = 'pending'
            job.last_error = 'waiting_for_child_batch_jobs'
            job.requested_at = _utcnow()
        return None

    now = _utcnow()
    active_batches = active_batch_query(db).filter(Batch.task_type_id == task_type_id)
    active_batch_subq = active_batches.with_entities(Batch.id, Batch.batch_decision).subquery()

    aggregate = (
        db.query(
            func.count(active_batch_subq.c.id).label('batch_count'),
            func.coalesce(func.sum(BatchAssetRollup.episode_count), 0).label('episode_count'),
            func.coalesce(func.sum(BatchAssetRollup.reviewed_count), 0).label('reviewed_count'),
            func.coalesce(func.sum(BatchAssetRollup.manual_pass_count), 0).label('manual_pass_count'),
            func.coalesce(func.sum(BatchAssetRollup.manual_fail_count), 0).label('manual_fail_count'),
            func.coalesce(func.sum(BatchAssetRollup.qualified_count), 0).label('qualified_count'),
            func.coalesce(func.sum(BatchAssetRollup.unqualified_count), 0).label('unqualified_count'),
            func.coalesce(func.sum(BatchAssetRollup.pending_dataset_count), 0).label('pending_dataset_count'),
            func.coalesce(func.sum(BatchAssetRollup.total_duration_sec), 0.0).label('total_duration_sec'),
            func.coalesce(func.sum(BatchAssetRollup.duration_covered_episode_count), 0).label('duration_covered_episode_count'),
            func.coalesce(func.sum(BatchAssetRollup.duration_missing_episode_count), 0).label('duration_missing_episode_count'),
            func.coalesce(func.sum(BatchAssetRollup.total_frame_count), 0).label('total_frame_count'),
            func.coalesce(func.sum(BatchAssetRollup.frame_covered_episode_count), 0).label('frame_covered_episode_count'),
            func.coalesce(func.sum(BatchAssetRollup.frame_missing_episode_count), 0).label('frame_missing_episode_count'),
            func.coalesce(func.sum(BatchAssetRollup.sampled_episode_count), 0).label('sampled_episode_count'),
            func.coalesce(func.sum(case((active_batch_subq.c.batch_decision == 'ACCEPTED', 1), else_=0)), 0).label('accepted_batch_count'),
            func.coalesce(func.sum(case((active_batch_subq.c.batch_decision == 'REJECTED', 1), else_=0)), 0).label('rejected_batch_count'),
            func.coalesce(func.sum(case((active_batch_subq.c.batch_decision == 'PENDING', 1), else_=0)), 0).label('pending_batch_count'),
            func.max(BatchAssetRollup.refreshed_at).label('latest_child_refreshed_at'),
            func.max(BatchAssetRollup.source_watermark).label('max_source_watermark'),
        )
        .select_from(active_batch_subq)
        .outerjoin(BatchAssetRollup, BatchAssetRollup.batch_id == active_batch_subq.c.id)
        .one()
    )

    batch_count = int(aggregate.batch_count or 0)
    episode_count = int(aggregate.episode_count or 0)
    reviewed_count = int(aggregate.reviewed_count or 0)
    not_reviewed_count = max(episode_count - reviewed_count, 0)
    source_watermark = (
        f'task:{task_type_id}:batches:{batch_count}:episodes:{episode_count}:'
        f'child:{aggregate.max_source_watermark or "none"}'
    )

    rollup = _query_or_pending(db, TaskAssetRollup, 'task_type_id', task_type_id)
    if not rollup:
        rollup = TaskAssetRollup(
            task_type_id=task_type_id,
            refreshed_at=now,
        )
        db.add(rollup)

    rollup.batch_count = batch_count
    rollup.episode_count = episode_count
    rollup.reviewed_count = reviewed_count
    rollup.not_reviewed_count = not_reviewed_count
    rollup.manual_pass_count = int(aggregate.manual_pass_count or 0)
    rollup.manual_fail_count = int(aggregate.manual_fail_count or 0)
    rollup.qualified_count = int(aggregate.qualified_count or 0)
    rollup.unqualified_count = int(aggregate.unqualified_count or 0)
    rollup.pending_dataset_count = int(aggregate.pending_dataset_count or 0)
    rollup.total_duration_sec = float(aggregate.total_duration_sec or 0.0)
    rollup.duration_covered_episode_count = int(aggregate.duration_covered_episode_count or 0)
    rollup.duration_missing_episode_count = int(aggregate.duration_missing_episode_count or 0)
    rollup.total_frame_count = int(aggregate.total_frame_count or 0)
    rollup.frame_covered_episode_count = int(aggregate.frame_covered_episode_count or 0)
    rollup.frame_missing_episode_count = int(aggregate.frame_missing_episode_count or 0)
    rollup.sampled_episode_count = int(aggregate.sampled_episode_count or 0)
    rollup.accepted_batch_count = int(aggregate.accepted_batch_count or 0)
    rollup.rejected_batch_count = int(aggregate.rejected_batch_count or 0)
    rollup.pending_batch_count = int(aggregate.pending_batch_count or 0)
    rollup.source_batch_count = batch_count
    rollup.source_watermark = source_watermark
    rollup.calculation_version = TASK_ROLLUP_VERSION
    rollup.refreshed_at = now

    db.flush()
    job = _query_or_pending(db, TaskAssetRecomputeJob, 'task_type_id', task_type_id)
    if job:
        job.status = 'pending' if job.rerun_requested else 'done'
        job.rerun_requested = False
        job.attempts += 1
        job.last_error = ''
        job.last_started_at = job.last_started_at or now
        job.last_finished_at = now

    return rollup


def mark_task_recompute_started(db: Session, task_type_id: str) -> TaskAssetRecomputeJob | None:
    job = db.query(TaskAssetRecomputeJob).filter(TaskAssetRecomputeJob.task_type_id == task_type_id).with_for_update().first()
    if not job:
        return None
    if job.status not in ('pending', 'failed'):
        return None
    job.status = 'running'
    job.rerun_requested = False
    job.last_started_at = _utcnow()
    job.last_error = ''
    return job


def mark_task_recompute_failed(db: Session, task_type_id: str, *, error: str) -> None:
    job = db.query(TaskAssetRecomputeJob).filter(TaskAssetRecomputeJob.task_type_id == task_type_id).first()
    if not job:
        return
    job.status = 'failed'
    job.attempts += 1
    job.last_error = error[:500]
    job.last_finished_at = _utcnow()


def rebuild_all_active_task_rollups(db: Session) -> int:
    task_type_ids = [
        item.id
        for item in db.query(TaskType.id).order_by(TaskType.id.asc()).all()
    ]
    # Prefer task types that currently hold active-scope batches, but also keep known task types rebuildable.
    active_task_ids = {
        item.task_type_id
        for item in active_batch_query(db).with_entities(Batch.task_type_id).distinct().all()
        if item.task_type_id
    }
    ordered_ids = list(dict.fromkeys([*sorted(active_task_ids), *task_type_ids]))
    rebuilt = 0
    for task_type_id in ordered_ids:
        if recompute_task_asset_rollup(db, task_type_id) is not None:
            rebuilt += 1
    return rebuilt


def process_pending_batch_recompute_jobs(db: Session, *, limit: int = 100) -> int:
    processed = 0
    while processed < limit:
        next_job = db.query(BatchAssetRecomputeJob).filter(
            BatchAssetRecomputeJob.status.in_(['pending', 'failed'])
        ).order_by(BatchAssetRecomputeJob.requested_at.asc()).first()
        if not next_job:
            break
        batch_id = next_job.batch_id
        try:
            started_job = mark_recompute_started(db, batch_id)
            if not started_job:
                db.rollback()
                continue
            recompute_batch_asset_rollup(db, batch_id)
            processed += 1
        except Exception as exc:
            db.rollback()
            mark_recompute_failed(db, batch_id, error=str(exc))
        finally:
            db.commit()
    return processed


def process_pending_task_recompute_jobs(db: Session, *, limit: int = 100) -> int:
    processed = 0
    while processed < limit:
        next_job = db.query(TaskAssetRecomputeJob).filter(
            TaskAssetRecomputeJob.status.in_(['pending', 'failed'])
        ).order_by(TaskAssetRecomputeJob.requested_at.asc()).first()
        if not next_job:
            break
        task_type_id = next_job.task_type_id
        try:
            started_job = mark_task_recompute_started(db, task_type_id)
            if not started_job:
                db.rollback()
                continue
            result = recompute_task_asset_rollup(db, task_type_id)
            if result is None and _task_has_pending_child_batch_jobs(db, task_type_id):
                # Keep pending and continue; do not count as processed success.
                db.commit()
                continue
            processed += 1
        except Exception as exc:
            db.rollback()
            mark_task_recompute_failed(db, task_type_id, error=str(exc))
        finally:
            db.commit()
    return processed


def process_pending_recompute_jobs(db: Session, *, limit: int = 100) -> int:
    """Process batch jobs first, then task jobs. Returns total processed count."""
    batch_limit = max(1, limit // 2) if limit > 1 else 1
    task_limit = max(1, limit - batch_limit)
    processed_batches = process_pending_batch_recompute_jobs(db, limit=batch_limit)
    remaining = max(0, limit - processed_batches)
    processed_tasks = process_pending_task_recompute_jobs(db, limit=max(task_limit, remaining))
    return processed_batches + processed_tasks


def rebuild_all_active_rollups(db: Session, *, scope: str = 'all') -> dict[str, int]:
    normalized_scope = (scope or 'all').strip().lower()
    if normalized_scope not in {'batch', 'task', 'all'}:
        normalized_scope = 'all'

    rebuilt_batches = 0
    rebuilt_tasks = 0
    if normalized_scope in {'batch', 'all'}:
        rebuilt_batches = rebuild_all_active_batch_rollups(db)
    if normalized_scope in {'task', 'all'}:
        rebuilt_tasks = rebuild_all_active_task_rollups(db)
    return {
        'scope': normalized_scope,
        'rebuiltBatchCount': rebuilt_batches,
        'rebuiltTaskCount': rebuilt_tasks,
    }


def data_assets_summary(db: Session) -> BatchAssetSummary:
    active_batches_query = active_batch_query(db)
    active_batches = active_batches_query.subquery()
    active_rollups = db.query(BatchAssetRollup).join(active_batches, BatchAssetRollup.batch_id == active_batches.c.id)

    summary_row = active_rollups.with_entities(
        func.coalesce(func.sum(BatchAssetRollup.episode_count), 0),
        func.coalesce(func.sum(BatchAssetRollup.total_duration_sec), 0.0),
        func.coalesce(func.sum(BatchAssetRollup.total_frame_count), 0),
        func.coalesce(func.sum(BatchAssetRollup.duration_covered_episode_count), 0),
        func.coalesce(func.sum(BatchAssetRollup.duration_missing_episode_count), 0),
        func.coalesce(func.sum(BatchAssetRollup.frame_covered_episode_count), 0),
        func.coalesce(func.sum(BatchAssetRollup.frame_missing_episode_count), 0),
        func.min(BatchAssetRollup.refreshed_at),
        func.max(BatchAssetRollup.refreshed_at),
    ).one()

    batch_count = active_batches_query.order_by(None).count()
    task_type_count = active_batch_query(db).with_entities(func.count(func.distinct(Batch.task_type_id))).scalar() or 0
    failure_reason_count = active_episode_query(db).with_entities(func.count(func.distinct(Episode.reason_code))).filter(
        Episode.reason_code != '-',
    ).scalar() or 0

    stale_batch_count = active_batch_query(db).outerjoin(BatchAssetRollup, BatchAssetRollup.batch_id == Batch.id).filter(
        (BatchAssetRollup.batch_id.is_(None))
        | (BatchAssetRollup.calculation_version != ROLLUP_VERSION)
    ).count()

    return BatchAssetSummary(
        episode_count=int(summary_row[0] or 0),
        batch_count=int(batch_count or 0),
        task_type_count=int(task_type_count),
        failure_reason_count=int(failure_reason_count),
        total_duration_sec=float(summary_row[1] or 0.0),
        total_frame_count=int(summary_row[2] or 0),
        duration_covered_episode_count=int(summary_row[3] or 0),
        duration_missing_episode_count=int(summary_row[4] or 0),
        frame_covered_episode_count=int(summary_row[5] or 0),
        frame_missing_episode_count=int(summary_row[6] or 0),
        stale_batch_count=int(stale_batch_count),
        oldest_refreshed_at=summary_row[7],
        newest_refreshed_at=summary_row[8],
        statistics_scope='active_list_active_batch_indexed_episodes',
        calculation_version=ROLLUP_VERSION,
    )


def data_asset_batch_rows(
    db: Session,
    *,
    page: int,
    page_size: int,
    keyword: str = '',
    task_type_id: str = '',
    batch_decision: str = '',
    qc_status: str = '',
):
    query = db.query(
        Batch.id.label('batch_id'),
        Batch.name.label('batch_name'),
        Batch.task_type_id.label('task_type_id'),
        TaskType.name.label('task_type_name'),
        Batch.qc_status.label('qc_status'),
        Batch.batch_decision.label('batch_decision'),
        Batch.batch_decision_reason.label('batch_decision_reason'),
        Batch.failure_rate.label('failure_rate'),
        Batch.reject_threshold.label('reject_threshold'),
        Batch.imported_at.label('created_at'),
        Batch.adjudicated_at.label('adjudicated_at'),
        BatchAssetRollup.episode_count.label('episode_count'),
        BatchAssetRollup.total_duration_sec.label('total_duration_sec'),
        BatchAssetRollup.duration_covered_episode_count.label('duration_covered_episode_count'),
        BatchAssetRollup.total_frame_count.label('total_frame_count'),
        BatchAssetRollup.frame_covered_episode_count.label('frame_covered_episode_count'),
        BatchAssetRollup.reviewed_count.label('reviewed_count'),
        BatchAssetRollup.qualified_count.label('qualified_count'),
        BatchAssetRollup.unqualified_count.label('unqualified_count'),
        BatchAssetRollup.manual_pass_count.label('manual_pass_count'),
        BatchAssetRollup.manual_fail_count.label('manual_fail_count'),
        BatchAssetRollup.pending_dataset_count.label('pending_dataset_count'),
        BatchAssetRollup.last_episode_updated_at.label('last_episode_updated_at'),
        BatchAssetRollup.refreshed_at.label('refreshed_at'),
    ).join(ListRecord, Batch.list_id == ListRecord.id).outerjoin(BatchAssetRollup, BatchAssetRollup.batch_id == Batch.id).outerjoin(TaskType, TaskType.id == Batch.task_type_id).filter(
        Batch.is_active == True,
        Batch.list_id.is_not(None),
        ListRecord.is_active == True,
    )

    normalized_keyword = keyword.strip().lower()
    if normalized_keyword:
        like_term = f'%{normalized_keyword}%'
        query = query.filter(
            func.lower(Batch.id).like(like_term)
            | func.lower(Batch.name).like(like_term)
            | func.lower(TaskType.name).like(like_term)
        )
    if task_type_id:
        query = query.filter(Batch.task_type_id == task_type_id)
    if batch_decision:
        query = query.filter(Batch.batch_decision == batch_decision)
    if qc_status:
        query = query.filter(Batch.qc_status == qc_status)

    total = query.order_by(None).count()
    items = query.order_by(Batch.imported_at.desc(), Batch.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def _task_row_is_stale(db: Session, *, task_type_id: str, rollup: TaskAssetRollup | None) -> bool:
    if rollup is None:
        return True
    if rollup.calculation_version != TASK_ROLLUP_VERSION:
        return True
    pending_job = db.query(TaskAssetRecomputeJob).filter(
        TaskAssetRecomputeJob.task_type_id == task_type_id,
        TaskAssetRecomputeJob.status.in_(['pending', 'running', 'failed']),
    ).first()
    if pending_job is not None:
        return True
    current_batch_count = active_batch_query(db).filter(Batch.task_type_id == task_type_id).count()
    if int(rollup.source_batch_count or 0) != int(current_batch_count or 0):
        return True
    return False


def data_asset_task_rows(
    db: Session,
    *,
    page: int,
    page_size: int,
    keyword: str = '',
    task_type_id: str = '',
    include_inactive: bool = False,
    stale_only: bool = False,
    sort_by: str = 'taskTypeName',
    sort_order: str = 'asc',
):
    query = db.query(
        TaskType.id.label('task_type_id'),
        TaskType.name.label('task_type_name'),
        TaskType.is_active.label('is_active'),
        TaskAssetRollup.batch_count.label('batch_count'),
        TaskAssetRollup.episode_count.label('episode_count'),
        TaskAssetRollup.reviewed_count.label('reviewed_count'),
        TaskAssetRollup.not_reviewed_count.label('not_reviewed_count'),
        TaskAssetRollup.manual_pass_count.label('manual_pass_count'),
        TaskAssetRollup.manual_fail_count.label('manual_fail_count'),
        TaskAssetRollup.qualified_count.label('qualified_count'),
        TaskAssetRollup.unqualified_count.label('unqualified_count'),
        TaskAssetRollup.pending_dataset_count.label('pending_dataset_count'),
        TaskAssetRollup.total_duration_sec.label('total_duration_sec'),
        TaskAssetRollup.duration_covered_episode_count.label('duration_covered_episode_count'),
        TaskAssetRollup.duration_missing_episode_count.label('duration_missing_episode_count'),
        TaskAssetRollup.total_frame_count.label('total_frame_count'),
        TaskAssetRollup.frame_covered_episode_count.label('frame_covered_episode_count'),
        TaskAssetRollup.frame_missing_episode_count.label('frame_missing_episode_count'),
        TaskAssetRollup.sampled_episode_count.label('sampled_episode_count'),
        TaskAssetRollup.accepted_batch_count.label('accepted_batch_count'),
        TaskAssetRollup.rejected_batch_count.label('rejected_batch_count'),
        TaskAssetRollup.pending_batch_count.label('pending_batch_count'),
        TaskAssetRollup.source_batch_count.label('source_batch_count'),
        TaskAssetRollup.source_watermark.label('source_watermark'),
        TaskAssetRollup.calculation_version.label('calculation_version'),
        TaskAssetRollup.refreshed_at.label('refreshed_at'),
        TaskAssetRecomputeJob.status.label('job_status'),
    ).outerjoin(TaskAssetRollup, TaskAssetRollup.task_type_id == TaskType.id).outerjoin(
        TaskAssetRecomputeJob, TaskAssetRecomputeJob.task_type_id == TaskType.id
    )

    if not include_inactive:
        query = query.filter(
            (TaskType.is_active == True)
            | (TaskType.id == 'task_type:unclassified')
        )

    normalized_keyword = keyword.strip().lower()
    if normalized_keyword:
        like_term = f'%{normalized_keyword}%'
        query = query.filter(
            func.lower(TaskType.id).like(like_term)
            | func.lower(TaskType.name).like(like_term)
        )
    if task_type_id:
        query = query.filter(TaskType.id == task_type_id)

    sort_map = {
        'taskTypeName': TaskType.name,
        'batchCount': TaskAssetRollup.batch_count,
        'episodeCount': TaskAssetRollup.episode_count,
        'qualifiedCount': TaskAssetRollup.qualified_count,
        'unqualifiedCount': TaskAssetRollup.unqualified_count,
        'pendingDatasetCount': TaskAssetRollup.pending_dataset_count,
        'totalDurationSec': TaskAssetRollup.total_duration_sec,
        'totalFrameCount': TaskAssetRollup.total_frame_count,
        'refreshedAt': TaskAssetRollup.refreshed_at,
    }
    sort_column = sort_map.get(sort_by, TaskType.name)
    if sort_order.lower() == 'desc':
        query = query.order_by(sort_column.desc(), TaskType.id.asc())
    else:
        query = query.order_by(sort_column.asc(), TaskType.id.asc())

    rows = query.all()
    enriched = []
    for row in rows:
        rollup = db.query(TaskAssetRollup).filter(TaskAssetRollup.task_type_id == row.task_type_id).first()
        stale = _task_row_is_stale(db, task_type_id=row.task_type_id, rollup=rollup)
        if stale_only and not stale:
            continue
        episode_count = int(row.episode_count or 0)
        reviewed_count = int(row.reviewed_count or 0)
        manual_pass_count = int(row.manual_pass_count or 0)
        manual_fail_count = int(row.manual_fail_count or 0)
        qualified_count = int(row.qualified_count or 0)
        unqualified_count = int(row.unqualified_count or 0)
        duration_covered = int(row.duration_covered_episode_count or 0)
        frame_covered = int(row.frame_covered_episode_count or 0)
        enriched.append({
            'task_type_id': row.task_type_id,
            'task_type_name': row.task_type_name,
            'is_active': bool(row.is_active),
            'batch_count': int(row.batch_count or 0),
            'episode_count': episode_count,
            'reviewed_count': reviewed_count,
            'not_reviewed_count': int(row.not_reviewed_count if row.not_reviewed_count is not None else max(episode_count - reviewed_count, 0)),
            'manual_pass_count': manual_pass_count,
            'manual_fail_count': manual_fail_count,
            'manual_pass_rate': _safe_rate(manual_pass_count, manual_pass_count + manual_fail_count),
            'manual_review_progress': _safe_rate(reviewed_count, episode_count),
            'qualified_count': qualified_count,
            'unqualified_count': unqualified_count,
            'pending_dataset_count': int(row.pending_dataset_count or 0),
            'final_qualified_rate': _safe_rate(qualified_count, qualified_count + unqualified_count),
            'final_adjudication_progress': _safe_rate(qualified_count + unqualified_count, episode_count),
            'total_duration_sec': float(row.total_duration_sec or 0.0),
            'duration_covered_episode_count': duration_covered,
            'duration_missing_episode_count': int(row.duration_missing_episode_count or 0),
            'duration_coverage_rate': _safe_rate(duration_covered, episode_count),
            'total_frame_count': int(row.total_frame_count or 0),
            'frame_covered_episode_count': frame_covered,
            'frame_missing_episode_count': int(row.frame_missing_episode_count or 0),
            'frame_coverage_rate': _safe_rate(frame_covered, episode_count),
            'sampled_episode_count': int(row.sampled_episode_count or 0),
            'accepted_batch_count': int(row.accepted_batch_count or 0),
            'rejected_batch_count': int(row.rejected_batch_count or 0),
            'pending_batch_count': int(row.pending_batch_count or 0),
            'source_batch_count': int(row.source_batch_count or 0),
            'source_watermark': row.source_watermark or '',
            'calculation_version': row.calculation_version or TASK_ROLLUP_VERSION,
            'refreshed_at': row.refreshed_at,
            'stale': stale,
            'job_status': row.job_status or '',
        })

    # Optional rate-based sorting after enrichment.
    rate_sort_keys = {
        'finalQualifiedRate': 'final_qualified_rate',
        'manualPassRate': 'manual_pass_rate',
    }
    if sort_by in rate_sort_keys:
        reverse = sort_order.lower() == 'desc'
        key_name = rate_sort_keys[sort_by]
        enriched.sort(key=lambda item: (item[key_name] is None, item[key_name] or 0.0), reverse=reverse)

    total = len(enriched)
    start = max(0, (page - 1) * page_size)
    end = start + page_size
    return enriched[start:end], total


def data_asset_task_detail(db: Session, task_type_id: str) -> dict | None:
    task_type = db.query(TaskType).filter(TaskType.id == task_type_id).first()
    if not task_type:
        return None
    items, _ = data_asset_task_rows(
        db,
        page=1,
        page_size=1,
        task_type_id=task_type_id,
        include_inactive=True,
    )
    if not items:
        return None
    row = items[0]
    child_batches, child_total = data_asset_batch_rows(
        db,
        page=1,
        page_size=10,
        task_type_id=task_type_id,
    )
    return {
        **row,
        'task_description': task_type.description,
        'arm_mode': task_type.arm_mode,
        'top_batches': child_batches,
        'top_batch_total': child_total,
    }
