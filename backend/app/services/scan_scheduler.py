from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services.data_assets import process_pending_recompute_jobs, rebuild_all_active_rollups

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


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
    _scheduler = BackgroundScheduler(daemon=True)
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
        '[scheduler] started recompute_interval=%ss reconcile=%02d:%02d (Asia/Shanghai)',
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
    logger.info('[scheduler] stopped')
