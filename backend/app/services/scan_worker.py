import json
import sys

from app.core.db import SessionLocal
from app.models import User
from app.services.scanner import backfill_manifest_metrics, resume_minio_scan


def main() -> None:
    db = SessionLocal()
    try:
        if len(sys.argv) >= 2 and sys.argv[1] == 'repair-manifest-metrics':
            operator_id = sys.argv[2] if len(sys.argv) >= 3 else ''
            bucket = sys.argv[3] if len(sys.argv) >= 4 else None
            operator = db.query(User).filter(User.id == operator_id).one() if operator_id else None
            result = backfill_manifest_metrics(db, operator=operator, bucket=bucket)
            db.commit()
            print(json.dumps(result, ensure_ascii=False))
            return

        if len(sys.argv) != 3:
            raise SystemExit(
                'usage: python -m app.services.scan_worker <scan_job_id> <operator_id>\n'
                '   or: python -m app.services.scan_worker repair-manifest-metrics [operator_id] [bucket]'
            )
        scan_job_id = sys.argv[1]
        operator_id = sys.argv[2]
        operator = db.query(User).filter(User.id == operator_id).one()
        resume_minio_scan(db, scan_job_id=scan_job_id, operator=operator)
    finally:
        db.close()


if __name__ == '__main__':
    main()
