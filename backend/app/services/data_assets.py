from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import BIGINT, case, cast, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Batch, BatchAssetRecomputeJob, BatchAssetRollup, Episode, ListRecord, TaskType


ROLLUP_VERSION = 'batch-asset-rollup-v1'
RECOMPUTE_REASONS = {
    'scan_sync',
    'episode_qc_changed',
    'dispatch_changed',
    'batch_relation_changed',
    'list_scope_changed',
    'manual_rebuild',
}


def _utcnow() -> datetime:
    return datetime.utcnow()


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
    )


def enqueue_batch_asset_recompute(db: Session, batch_id: str, *, reason: str) -> None:
    normalized_reason = reason if reason in RECOMPUTE_REASONS else 'manual_rebuild'
    now = _utcnow()
    stmt = insert(BatchAssetRecomputeJob).values(
        batch_id=batch_id,
        reason=normalized_reason,
        requested_at=now,
        status='pending',
        attempts=0,
        last_error='',
        last_started_at=None,
        last_finished_at=None,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[BatchAssetRecomputeJob.batch_id],
        set_={
            'reason': normalized_reason,
            'requested_at': now,
            'status': 'pending',
            'last_error': '',
        },
    )
    db.execute(stmt)


def enqueue_list_scope_recompute(db: Session, list_id: str, *, reason: str) -> int:
    batch_ids = [item.id for item in db.query(Batch.id).filter(Batch.list_id == list_id).all()]
    for batch_id in batch_ids:
        enqueue_batch_asset_recompute(db, batch_id, reason=reason)
    return len(batch_ids)


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
    ).filter(Episode.batch_id == batch_id).one()

    source_updated_at = aggregate.last_episode_updated_at.isoformat() if aggregate.last_episode_updated_at else 'none'
    source_watermark = f'episodes:{aggregate.episode_count}:updated:{source_updated_at}'

    rollup = db.query(BatchAssetRollup).filter(BatchAssetRollup.batch_id == batch_id).first()
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

    job = db.query(BatchAssetRecomputeJob).filter(BatchAssetRecomputeJob.batch_id == batch_id).first()
    if job:
        job.status = 'done'
        job.attempts += 1
        job.last_error = ''
        job.last_started_at = job.last_started_at or now
        job.last_finished_at = now

    return rollup


def mark_recompute_started(db: Session, batch_id: str) -> BatchAssetRecomputeJob | None:
    job = db.query(BatchAssetRecomputeJob).filter(BatchAssetRecomputeJob.batch_id == batch_id).with_for_update().first()
    if not job:
        return None
    if job.status not in ('pending', 'failed'):
        return None
    job.status = 'running'
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


def process_pending_recompute_jobs(db: Session, *, limit: int = 100) -> int:
    processed = 0
    while processed < limit:
        next_job = db.query(BatchAssetRecomputeJob).filter(
            BatchAssetRecomputeJob.status.in_(['pending', 'failed'])
        ).order_by(BatchAssetRecomputeJob.requested_at.asc()).with_for_update(skip_locked=True).first()
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
