import threading
from datetime import datetime

from app.core.db import SessionLocal
from app.models import ScanJob, User
from app.services.scanner import resume_minio_scan


def enqueue_scan_job(scan_job_id: str, operator_id: str) -> None:
    worker = threading.Thread(
        target=process_scan_job,
        args=(scan_job_id, operator_id),
        name=f'scan-job-{scan_job_id}',
        daemon=True,
    )
    worker.start()


def process_scan_job(scan_job_id: str, operator_id: str) -> None:
    db = SessionLocal()
    try:
        operator = db.query(User).filter(User.id == operator_id).one()
        resume_minio_scan(db, scan_job_id=scan_job_id, operator=operator)
    except Exception as exc:
        db.rollback()
        failed_job = db.query(ScanJob).filter(ScanJob.id == scan_job_id).first()
        if failed_job:
            failed_job.status = 'failed'
            failed_job.error_detail = str(exc)
            failed_job.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
