from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.user import User

_scheduler: BackgroundScheduler | None = None


def _scan_job() -> None:
    settings = get_settings()
    bucket = settings.minio_default_bucket
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.role == 'admin', User.is_active == True).first()
        if not admin:
            print('[scan_cron] no active admin user found, skipping scan', flush=True)
            return
        print(f'[scan_cron] starting scan bucket={bucket} operator={admin.username}', flush=True)
        from app.services.scanner import run_minio_scan
        job = run_minio_scan(db, bucket=bucket, operator=admin)
        print(f'[scan_cron] scan done job_id={job.id} episodes={job.total_episodes}', flush=True)
    except Exception:
        import traceback
        traceback.print_exc()
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
    _scheduler.add_job(_scan_job, CronTrigger(hour=hour, minute=minute), id='daily_scan')
    _scheduler.start()
    print(f'[scan_cron] scheduler started, daily at {hour:02d}:{minute:02d} (UTC)', flush=True)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    print('[scan_cron] scheduler stopped', flush=True)
