from __future__ import annotations

import sys

from app.core.db import SessionLocal
from app.services.data_assets import process_pending_recompute_jobs, rebuild_all_active_batch_rollups


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else 'process'
    db = SessionLocal()
    try:
        if command == 'rebuild-all':
            count = rebuild_all_active_batch_rollups(db)
            db.commit()
            print(f'rebuilt={count}')
            return
        count = process_pending_recompute_jobs(db)
        print(f'processed={count}')
    finally:
        db.close()


if __name__ == '__main__':
    main()
