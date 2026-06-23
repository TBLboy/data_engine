from app.core.db import SessionLocal
from app.models import ScanJob, User
from app.services.scanner import resume_minio_scan
from datetime import datetime
import traceback


def process_scan_job(scan_job_id: str, operator_id: str) -> None:
    db = SessionLocal()
    try:
        operator = db.query(User).filter(User.id == operator_id).one()
        resume_minio_scan(db, scan_job_id=scan_job_id, operator=operator)
    except Exception as exc:
        traceback.print_exc()
        db.rollback()
        failed_job = db.query(ScanJob).filter(ScanJob.id == scan_job_id).first()
        if failed_job:
            failed_job.status = 'failed'
            failed_job.error_detail = str(exc)
            failed_job.finished_at = datetime.utcnow()
            db.commit()
        raise
    finally:
        db.close()
