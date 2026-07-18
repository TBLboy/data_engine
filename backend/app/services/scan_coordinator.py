from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import DiscoveredPrefix, ListRecord, ScanJob, ScanPrefixState, ScanShard
from app.services.business_resolver import list_id
from app.services.data_assets import process_pending_recompute_jobs
from app.services.scan_queue import ACTIVE_JOB_STATUSES, add_scan_shard, create_or_get_scan_job


logger = logging.getLogger(__name__)
ADVISORY_LOCK_ID = 0x5343414E5633


def _utcnow() -> datetime:
    return datetime.utcnow()


def _adaptive_next_scan(now: datetime, unchanged: int) -> datetime:
    if unchanged <= 0:
        return now + timedelta(minutes=30)
    if unchanged == 1:
        return now + timedelta(hours=2)
    if unchanged == 2:
        return now + timedelta(hours=12)
    if unchanged == 3:
        return now + timedelta(days=1)
    return now + timedelta(days=7)


def _scheduled_job_id(mode: str, bucket: str, local_now: datetime) -> str:
    bucket_key = ''.join(char if char.isalnum() else '_' for char in bucket)[:24]
    period = local_now.strftime('%Y%m%d') if mode == 'smart' else local_now.strftime('%G%V')
    return f'scan_scheduled_{mode}_{bucket_key}_{period}'


def ensure_scheduled_jobs(db: Session, *, now: datetime | None = None) -> int:
    settings = get_settings()
    local_now = (now or datetime.now(ZoneInfo(settings.app_timezone))).astimezone(ZoneInfo(settings.app_timezone))
    created = 0
    daily_due = (local_now.hour, local_now.minute) >= (settings.scan_cron_hour, settings.scan_cron_minute)
    if daily_due:
        job, was_created = create_or_get_scan_job(
            db,
            bucket=settings.minio_default_bucket,
            mode='smart',
            triggered_by='system',
            trigger_source='scheduled',
            job_id=_scheduled_job_id('smart', settings.minio_default_bucket, local_now),
        )
        del job
        created += int(was_created)

    day_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
    full_day = day_map.get(settings.scan_full_cron_day_of_week.lower(), 6)
    full_due = local_now.weekday() == full_day and (
        local_now.hour,
        local_now.minute,
    ) >= (settings.scan_full_cron_hour, settings.scan_full_cron_minute)
    if full_due:
        job, was_created = create_or_get_scan_job(
            db,
            bucket=settings.minio_default_bucket,
            mode='full',
            triggered_by='system',
            trigger_source='scheduled',
            priority=90,
            job_id=_scheduled_job_id('full', settings.minio_default_bucket, local_now),
        )
        del job
        created += int(was_created)
    return created


def _upsert_prefix_state(db: Session, *, bucket: str, prefix: str) -> ScanPrefixState:
    state = db.query(ScanPrefixState).filter(
        ScanPrefixState.bucket == bucket,
        ScanPrefixState.prefix == prefix,
    ).first()
    if state is None:
        record_exists = db.query(ListRecord.id).filter(
            ListRecord.bucket == bucket,
            ListRecord.list_prefix == prefix,
        ).first()
        state = ScanPrefixState(
            bucket=bucket,
            prefix=prefix,
            list_id=list_id(bucket, prefix) if record_exists else None,
            scan_policy='adaptive',
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(state)
    return state


def expand_discovery_results(db: Session) -> int:
    jobs = db.query(ScanJob).join(ScanShard, ScanShard.scan_job_id == ScanJob.id).filter(
        ScanJob.status.in_(('queued', 'discovering', 'running')),
        ScanShard.shard_type == 'namespace_discovery',
        ScanShard.status == 'succeeded',
    ).all()
    created = 0
    now = _utcnow()
    for job in jobs:
        existing_list_shard = db.query(ScanShard.id).filter(
            ScanShard.scan_job_id == job.id,
            ScanShard.shard_type.in_(('list', 'list_missing_confirmation')),
        ).first()
        if existing_list_shard is not None:
            continue
        candidates = db.query(DiscoveredPrefix).filter(
            DiscoveredPrefix.scan_job_id == job.id,
            DiscoveredPrefix.bucket == job.bucket,
            DiscoveredPrefix.is_list_candidate == True,
        ).order_by(DiscoveredPrefix.prefix.asc()).all()
        discovered = {item.prefix for item in candidates}
        known_lists = db.query(ListRecord).filter(ListRecord.bucket == job.bucket).all()
        known_by_prefix = {item.list_prefix: item for item in known_lists}
        selected: set[str] = set()
        if job.scan_mode == 'full':
            selected.update(discovered)
            selected.update(known_by_prefix)
        else:
            selected.update(prefix for prefix in discovered if prefix not in known_by_prefix)
            selected.update(
                item.list_prefix for item in known_lists
                if item.source_status != 'present'
            )
            due_states = db.query(ScanPrefixState).filter(
                ScanPrefixState.bucket == job.bucket,
                ScanPrefixState.next_scan_at <= now,
                ScanPrefixState.scan_policy != 'manual',
            ).all()
            selected.update(item.prefix for item in due_states)
            if not selected:
                selected.update(discovered)

        for prefix in sorted(selected):
            state = _upsert_prefix_state(db, bucket=job.bucket, prefix=prefix)
            state.updated_at = now
            if prefix in discovered:
                add_scan_shard(db, job=job, shard_type='list', prefix=prefix)
            else:
                add_scan_shard(db, job=job, shard_type='list_missing_confirmation', prefix=prefix, priority=50)
            created += 1
        job.total_prefixes = len(candidates)
        job.total_shards = db.query(ScanShard).filter(ScanShard.scan_job_id == job.id).count()
        job.status = 'running' if selected else 'queued'
        job.updated_at = now
    return created


def reclaim_expired_leases(db: Session) -> int:
    now = _utcnow()
    shards = db.query(ScanShard).filter(
        ScanShard.status == 'running',
        ScanShard.lease_expires_at < now,
    ).with_for_update().all()
    for shard in shards:
        shard.lease_owner = ''
        shard.lease_expires_at = None
        shard.error_detail = 'worker lease expired'
        shard.updated_at = now
        if shard.attempt < shard.max_attempts:
            shard.status = 'retry_wait'
            shard.next_retry_at = now + timedelta(seconds=30)
        else:
            shard.status = 'timeout'
            shard.finished_at = now
    return len(shards)


def _update_prefix_state_from_shard(db: Session, shard: ScanShard, now: datetime) -> None:
    if shard.shard_type != 'list' or shard.status != 'succeeded':
        return
    state = _upsert_prefix_state(db, bucket=shard.bucket, prefix=shard.prefix)
    shard_finished = shard.finished_at or now
    if state.last_success_at is not None and state.last_success_at >= shard_finished:
        return
    changed = shard.changed_episodes > 0 or shard.new_episodes > 0
    state.list_id = list_id(shard.bucket, shard.prefix)
    state.last_success_at = shard_finished
    state.last_changed_at = shard_finished if changed else state.last_changed_at
    state.consecutive_unchanged = 0 if changed else state.consecutive_unchanged + 1
    state.last_episode_count = shard.processed_episodes
    state.last_object_count = shard.processed_objects
    if shard.started_at and shard.finished_at:
        state.last_duration_seconds = max((shard.finished_at - shard.started_at).total_seconds(), 0.0)
    state.last_error = ''
    if state.scan_policy == 'adaptive':
        state.next_scan_at = _adaptive_next_scan(now, state.consecutive_unchanged)
    elif state.scan_policy == 'realtime':
        state.next_scan_at = now + timedelta(minutes=30)
    elif state.scan_policy == 'daily':
        state.next_scan_at = now + timedelta(days=1)
    elif state.scan_policy == 'weekly':
        state.next_scan_at = now + timedelta(days=7)
    else:
        state.next_scan_at = None
    state.updated_at = now


def aggregate_jobs(db: Session) -> int:
    now = _utcnow()
    updated = 0
    jobs = db.query(ScanJob).filter(ScanJob.status.in_(ACTIVE_JOB_STATUSES)).with_for_update().all()
    for job in jobs:
        shards = db.query(ScanShard).filter(ScanShard.scan_job_id == job.id).all()
        if not shards:
            continue
        for shard in shards:
            _update_prefix_state_from_shard(db, shard, now)
        counts = {status: 0 for status in (
            'pending', 'running', 'retry_wait', 'succeeded', 'skipped', 'failed', 'cancelled', 'timeout'
        )}
        for shard in shards:
            counts[shard.status] = counts.get(shard.status, 0) + 1
        job.total_shards = len(shards)
        job.succeeded_shards = counts['succeeded']
        job.failed_shards = counts['failed'] + counts['timeout']
        job.running_shards = counts['running']
        job.skipped_shards = counts['skipped'] + counts['cancelled']
        job.confirmed_lists = sum(1 for item in shards if item.shard_type == 'list' and item.status == 'succeeded')
        job.total_episodes = sum(item.processed_episodes for item in shards if item.shard_type == 'list')
        job.new_episodes = sum(item.new_episodes for item in shards if item.shard_type == 'list')
        job.heartbeat_at = now
        job.updated_at = now
        active_count = counts['pending'] + counts['running'] + counts['retry_wait']
        if active_count:
            job.status = 'cancelling' if job.cancel_requested_at else (
                'discovering' if any(item.shard_type == 'namespace_discovery' and item.status != 'succeeded' for item in shards)
                else 'running'
            )
        else:
            failed = counts['failed'] + counts['timeout']
            succeeded = counts['succeeded']
            if job.cancel_requested_at and counts['cancelled']:
                job.status = 'cancelled'
            elif failed and succeeded:
                job.status = 'partially_failed'
            elif failed:
                job.status = 'failed'
            else:
                job.status = 'succeeded'
            errors = [item.error_detail for item in shards if item.error_detail and item.status in ('failed', 'timeout')]
            job.error_summary = '\n'.join(errors[:10])[:4000]
            job.error_detail = (
                f'shards={len(shards)} succeeded={succeeded} failed={failed} '
                f'episodes={job.total_episodes} new={job.new_episodes}'
            )[:500]
            job.finished_at = now
            job.active_key = None
        updated += 1
    return updated


def coordinator_tick(db: Session) -> dict[str, int]:
    bind = db.get_bind()
    if bind.dialect.name == 'postgresql':
        locked = bool(db.execute(text('SELECT pg_try_advisory_xact_lock(:key)'), {'key': ADVISORY_LOCK_ID}).scalar())
        if not locked:
            return {'scheduled': 0, 'reclaimed': 0, 'expanded': 0, 'aggregated': 0, 'recomputed': 0}
    result = {
        'scheduled': ensure_scheduled_jobs(db),
        'reclaimed': reclaim_expired_leases(db),
        'expanded': expand_discovery_results(db),
        'aggregated': aggregate_jobs(db),
        'recomputed': process_pending_recompute_jobs(db, limit=get_settings().data_assets_recompute_batch_limit),
    }
    return result


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO)
    logger.info('scan coordinator started interval=%ss', settings.scan_coordinator_interval_seconds)
    while True:
        db = SessionLocal()
        try:
            result = coordinator_tick(db)
            db.commit()
            if any(result.values()):
                logger.info('scan coordinator tick %s', result)
        except Exception:
            db.rollback()
            logger.exception('scan coordinator tick failed')
        finally:
            db.close()
        time.sleep(max(1, settings.scan_coordinator_interval_seconds))


if __name__ == '__main__':
    main()
