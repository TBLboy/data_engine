from __future__ import annotations

import sys

from app.core.db import SessionLocal
from app.services.data_assets import process_pending_recompute_jobs, rebuild_all_active_rollups


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else 'process'
    scope = sys.argv[2] if len(sys.argv) > 2 else 'all'
    db = SessionLocal()
    try:
        if command == 'rebuild-all':
            result = rebuild_all_active_rollups(db, scope=scope)
            db.commit()
            print(
                f"scope={result['scope']} rebuilt_batches={result['rebuiltBatchCount']} "
                f"rebuilt_tasks={result['rebuiltTaskCount']}"
            )
            return
        count = process_pending_recompute_jobs(db)
        print(f'processed={count}')
    finally:
        db.close()


if __name__ == '__main__':
    main()
