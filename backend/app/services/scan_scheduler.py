from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services.data_assets import process_pending_recompute_jobs, rebuild_all_active_rollups
from app.models.user import User

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _scan_job() -> None:
    settings = get_settings()
    bucket = settings.minio_default_bucket
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.role == 'admin', User.is_active == True).first()
        if not admin:
            logger.warning('[scan_cron] no active admin user found, skipping scan')
            return
        logger.info('[scan_cron] starting scan bucket=%s operator=%s', bucket, admin.username)
        from app.services.scanner import run_minio_scan
        job = run_minio_scan(db, bucket=bucket, operator=admin)
        logger.info('[scan_cron] scan done job_id=%s episodes=%s', job.id, job.total_episodes)
    except Exception:
        logger.exception('[scan_cron] scan failed')
    finally:
        db.close()


def _data_assets_recompute_job() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        processed = process_pending_recompute_jobs(db, limit=settings.data_assets_recompute_batch_limit)
        if processed:
            logger.info('[data_assets_recompute] processed=%s', processed)
    except Exception:
        logger.exception('[data_assets_recompute] failed')
    finally:
        db.close()


def _data_assets_reconcile_job() -> None:
    db = SessionLocal()
    try:
        result = rebuild_all_active_rollups(db, scope='all')
        rebuilt = result['rebuiltBatchCount'] + result['rebuiltTaskCount']
        db.commit()
        logger.info('[data_assets_reconcile] rebuilt=%s', rebuilt)
    except Exception:
        db.rollback()
        logger.exception('[data_assets_reconcile] failed')
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    settings = get_settings()
    hour = settings.scan_cron_hour
    minute = settings.scan_cron_minute
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(_scan_job, CronTrigger(hour=hour, minute=minute, timezone='Asia/Shanghai'), id='daily_scan')
    _scheduler.add_job(
        _data_assets_recompute_job,
        IntervalTrigger(seconds=max(5, settings.data_assets_recompute_interval_seconds), timezone='Asia/Shanghai'),
        id='data_assets_recompute',
        max_instances=1,
        coalesce=True,
    )
    _scheduler.add_job(
        _data_assets_reconcile_job,
        CronTrigger(
            hour=settings.data_assets_reconcile_cron_hour,
            minute=settings.data_assets_reconcile_cron_minute,
            timezone='Asia/Shanghai',
        ),
        id='data_assets_reconcile',
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        '[scan_cron] scheduler started, daily_scan=%02d:%02d recompute_interval=%ss reconcile=%02d:%02d (Asia/Shanghai)',
        hour,
        minute,
        max(5, settings.data_assets_recompute_interval_seconds),
        settings.data_assets_reconcile_cron_hour,
        settings.data_assets_reconcile_cron_minute,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info('[scan_cron] scheduler stopped')
