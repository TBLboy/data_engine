from app.core.db import SessionLocal
from app.models import User
from app.services.scanner import resume_minio_scan
import sys


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit('usage: python -m app.services.scan_worker <scan_job_id> <operator_id>')
    scan_job_id = sys.argv[1]
    operator_id = sys.argv[2]
    db = SessionLocal()
    try:
        operator = db.query(User).filter(User.id == operator_id).one()
        resume_minio_scan(db, scan_job_id=scan_job_id, operator=operator)
    finally:
        db.close()


if __name__ == '__main__':
    main()
