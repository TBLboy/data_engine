from __future__ import annotations

import json
import logging
import multiprocessing
import os
import socket
import sys
import time
from datetime import datetime, timedelta

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import DiscoveredPrefix, EpisodeInventory, ListRecord, ScanJob, ScanShard, User
from app.services.business_resolver import mark_list_not_found, resolve_list_snapshot
from app.services.list_snapshot import build_list_snapshot
from app.services.minio_client import get_minio_service
from app.services.namespace_discovery import discover_namespaces
from app.services.scan_queue import (
    add_scan_shard,
    cancel_running_shard,
    claim_next_shard,
    complete_shard,
    fail_shard,
    heartbeat_shard,
    should_cancel_shard,
)
from app.services.scanner import backfill_manifest_metrics


logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _lock_owned_shard(db, *, shard_id: int, worker_id: str) -> ScanShard:
    shard = db.query(ScanShard).filter(
        ScanShard.id == shard_id,
        ScanShard.status == 'running',
        ScanShard.lease_owner == worker_id,
    ).with_for_update().first()
    if shard is None or shard.lease_expires_at is None or shard.lease_expires_at <= _utcnow():
        raise RuntimeError('shard lease was lost before publication')
    return shard


def _publish_discovery(shard_id: int, worker_id: str, result) -> None:
    db = SessionLocal()
    try:
        shard = _lock_owned_shard(db, shard_id=shard_id, worker_id=worker_id)
        if not result.enumeration_complete:
            raise RuntimeError('incomplete namespace discovery cannot be published')
        for observation in result.observations:
            record = db.query(DiscoveredPrefix).filter(
                DiscoveredPrefix.bucket == shard.bucket,
                DiscoveredPrefix.prefix == observation.prefix,
            ).first()
            if record is None:
                record = DiscoveredPrefix(
                    scan_job_id=shard.scan_job_id,
                    bucket=shard.bucket,
                    prefix=observation.prefix,
                    depth=observation.depth,
                    has_raw_child=observation.has_raw_child,
                    has_processed_child=observation.has_processed_child,
                    has_episode_grandchild=observation.has_episode_grandchild,
                    is_list_candidate=observation.is_list_candidate,
                    first_seen_scan_id=shard.scan_job_id,
                    last_seen_scan_id=shard.scan_job_id,
                )
                db.add(record)
            else:
                record.scan_job_id = shard.scan_job_id
                record.depth = observation.depth
                record.has_raw_child = observation.has_raw_child
                record.has_processed_child = observation.has_processed_child
                record.has_episode_grandchild = observation.has_episode_grandchild
                record.is_list_candidate = observation.is_list_candidate
                record.last_seen_scan_id = shard.scan_job_id
        if not complete_shard(db, shard_id=shard.id, worker_id=worker_id):
            raise RuntimeError('shard lease was lost while completing discovery')
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _existing_fingerprints(shard: ScanShard) -> dict[str, tuple[str, str]]:
    db = SessionLocal()
    try:
        query = db.query(EpisodeInventory).join(
            ListRecord, EpisodeInventory.list_id == ListRecord.id
        ).filter(
            ListRecord.bucket == shard.bucket,
            ListRecord.list_prefix == shard.prefix,
        )
        if shard.range_start:
            query = query.filter(EpisodeInventory.episode_name >= shard.range_start)
        if shard.range_end:
            query = query.filter(EpisodeInventory.episode_name < shard.range_end)
        return {
            item.episode_name: (item.raw_content_fingerprint, item.processed_content_fingerprint)
            for item in query.all()
        }
    finally:
        db.close()


def _publish_list(shard_id: int, worker_id: str, snapshot) -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        shard = _lock_owned_shard(db, shard_id=shard_id, worker_id=worker_id)
        job = db.query(ScanJob).filter(ScanJob.id == shard.scan_job_id).first()
        if job is None:
            raise RuntimeError('scan job no longer exists')
        existing_list = db.query(ListRecord).filter(
            ListRecord.bucket == shard.bucket,
            ListRecord.list_prefix == shard.prefix,
        ).first()
        if not snapshot.episodes:
            if existing_list is not None:
                mark_list_not_found(
                    db,
                    bucket=shard.bucket,
                    list_prefix=shard.prefix,
                    shard_id=shard.id,
                    confirmation_seconds=settings.scan_missing_confirmation_seconds,
                )
                db.flush()
                if existing_list.source_status == 'suspect_missing':
                    add_scan_shard(
                        db,
                        job=job,
                        shard_type='list_missing_confirmation',
                        prefix=shard.prefix,
                        priority=50,
                        next_retry_at=_utcnow() + timedelta(seconds=settings.scan_missing_confirmation_seconds),
                        suffix=f'confirm-after-{shard.id}',
                    )
            else:
                raise RuntimeError('empty snapshot for unknown prefix — refusing to create empty List/Batch')
        else:
            resolution = resolve_list_snapshot(
                db,
                scan_job=job,
                shard_id=shard.id,
                snapshot=snapshot,
                missing_confirmation_seconds=settings.scan_missing_confirmation_seconds,
            )
            if resolution.needs_missing_confirmation:
                add_scan_shard(
                    db,
                    job=job,
                    shard_type='list_missing_confirmation',
                    prefix=shard.prefix,
                    priority=50,
                    next_retry_at=_utcnow() + timedelta(seconds=settings.scan_missing_confirmation_seconds),
                    suffix=f'confirm-after-{shard.id}',
                )
        if not complete_shard(
            db,
            shard_id=shard.id,
            worker_id=worker_id,
            processed_objects=snapshot.object_count,
            processed_episodes=len(snapshot.episodes),
            changed_episodes=(resolution.changed_episode_count if snapshot.episodes else 0),
            new_episodes=(resolution.new_episode_count if snapshot.episodes else 0),
        ):
            raise RuntimeError('shard lease was lost while completing List publication')
        job.total_shards = db.query(ScanShard).filter(ScanShard.scan_job_id == job.id).count()
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def execute_shard_child(shard_id: int, worker_id: str) -> None:
    db = SessionLocal()
    try:
        shard = db.query(ScanShard).filter(
            ScanShard.id == shard_id,
            ScanShard.status == 'running',
            ScanShard.lease_owner == worker_id,
        ).first()
        if shard is None:
            raise RuntimeError('claimed shard not found')
        shard_data = {
            'id': shard.id,
            'type': shard.shard_type,
            'bucket': shard.bucket,
            'prefix': shard.prefix,
            'range_start': shard.range_start,
            'range_end': shard.range_end,
        }
    finally:
        db.close()

    try:
        service = get_minio_service()
        if shard_data['type'] == 'namespace_discovery':
            result = discover_namespaces(service, shard_data['bucket'], root_prefix=shard_data['prefix'])
            _publish_discovery(shard_data['id'], worker_id, result)
            return
        if shard_data['type'] in ('list', 'list_missing_confirmation'):
            db = SessionLocal()
            try:
                detached_shard = db.query(ScanShard).filter(ScanShard.id == shard_data['id']).one()
                fingerprints = _existing_fingerprints(detached_shard)
            finally:
                db.close()
            snapshot = build_list_snapshot(
                service,
                shard_data['bucket'],
                shard_data['prefix'],
                existing_fingerprints=fingerprints,
                range_start=shard_data['range_start'],
                range_end=shard_data['range_end'],
            )
            _publish_list(shard_data['id'], worker_id, snapshot)
            return
        raise RuntimeError(f'unsupported shard type: {shard_data["type"]}')
    except Exception as exc:
        db = SessionLocal()
        try:
            fail_shard(
                db,
                shard_id=shard_id,
                worker_id=worker_id,
                error=f'{type(exc).__name__}: {exc}',
            )
            db.commit()
        finally:
            db.close()
        raise


def _worker_id() -> str:
    return f'{socket.gethostname()}:{os.getpid()}'


def run_worker_forever() -> None:
    settings = get_settings()
    worker_id = _worker_id()
    context = multiprocessing.get_context('spawn')
    logger.info('scan worker started id=%s', worker_id)
    while True:
        db = SessionLocal()
        try:
            shard = claim_next_shard(db, worker_id=worker_id, lease_seconds=settings.scan_worker_lease_seconds)
            db.commit()
            shard_id = shard.id if shard is not None else None
            timeout_seconds = shard.timeout_seconds if shard is not None else settings.scan_shard_timeout_seconds
        except Exception:
            db.rollback()
            logger.exception('failed to claim scan shard')
            shard_id = None
            timeout_seconds = settings.scan_shard_timeout_seconds
        finally:
            db.close()
        if shard_id is None:
            time.sleep(max(0.2, settings.scan_worker_poll_seconds))
            continue

        process = context.Process(target=execute_shard_child, args=(shard_id, worker_id))
        process.start()
        started = time.monotonic()
        last_heartbeat = 0.0
        cancelled = False
        timed_out = False
        while process.is_alive():
            elapsed = time.monotonic() - started
            if elapsed - last_heartbeat >= settings.scan_worker_heartbeat_seconds:
                db = SessionLocal()
                try:
                    cancelled = should_cancel_shard(db, shard_id=shard_id, worker_id=worker_id)
                    if not cancelled:
                        heartbeat_shard(
                            db,
                            shard_id=shard_id,
                            worker_id=worker_id,
                            lease_seconds=settings.scan_worker_lease_seconds,
                        )
                    db.commit()
                finally:
                    db.close()
                last_heartbeat = elapsed
            timed_out = elapsed >= timeout_seconds
            if cancelled or timed_out:
                process.terminate()
                process.join(5)
                if process.is_alive():
                    process.kill()
                break
            process.join(0.5)
        process.join()

        db = SessionLocal()
        try:
            if cancelled:
                cancel_running_shard(db, shard_id=shard_id, worker_id=worker_id)
            elif timed_out:
                fail_shard(db, shard_id=shard_id, worker_id=worker_id, error='shard wall-clock timeout', timed_out=True)
            elif process.exitcode not in (0, None):
                fail_shard(db, shard_id=shard_id, worker_id=worker_id, error=f'shard child exited with code {process.exitcode}')
            db.commit()
        finally:
            db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) >= 2 and sys.argv[1] == 'repair-manifest-metrics':
        db = SessionLocal()
        try:
            operator_id = sys.argv[2] if len(sys.argv) >= 3 else ''
            bucket = sys.argv[3] if len(sys.argv) >= 4 else None
            operator = db.query(User).filter(User.id == operator_id).one() if operator_id else None
            result = backfill_manifest_metrics(db, operator=operator, bucket=bucket)
            db.commit()
            print(json.dumps(result, ensure_ascii=False))
        finally:
            db.close()
        return
    run_worker_forever()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
