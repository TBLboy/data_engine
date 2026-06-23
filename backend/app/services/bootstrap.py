from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import BASE_DIR
from app.core.db import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import User


def _ensure_sqlite_directory() -> None:
    database_url = str(engine.url)
    if not database_url.startswith('sqlite:///'):
        return
    db_path = Path(database_url.removeprefix('sqlite:///'))
    db_path.parent.mkdir(parents=True, exist_ok=True)


def _sqlite_column_exists(table_name: str, column_name: str) -> bool:
    with engine.connect() as conn:
        rows = conn.execute(text(f'PRAGMA table_info({table_name})')).mappings().all()
    return any(row['name'] == column_name for row in rows)


def _sqlite_backfill_schema() -> None:
    database_url = str(engine.url)
    if not database_url.startswith('sqlite:///'):
        return

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if 'users' in existing_tables:
        with engine.begin() as conn:
            if not _sqlite_column_exists('users', 'is_active'):
                conn.execute(text('ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1'))
            if not _sqlite_column_exists('users', 'password_changed_at'):
                conn.execute(text('ALTER TABLE users ADD COLUMN password_changed_at DATETIME'))

    if 'episodes' in existing_tables:
        episode_columns = {
            'source_path': "ALTER TABLE episodes ADD COLUMN source_path VARCHAR(255) NOT NULL DEFAULT ''",
            'source_hash': "ALTER TABLE episodes ADD COLUMN source_hash VARCHAR(64) NOT NULL DEFAULT ''",
            'ingest_status': "ALTER TABLE episodes ADD COLUMN ingest_status VARCHAR(32) NOT NULL DEFAULT 'indexed'",
            'in_candidate_pool': 'ALTER TABLE episodes ADD COLUMN in_candidate_pool INTEGER NOT NULL DEFAULT 1',
            'sampled_for_qc': 'ALTER TABLE episodes ADD COLUMN sampled_for_qc INTEGER NOT NULL DEFAULT 0',
        }
        with engine.begin() as conn:
            for column_name, ddl in episode_columns.items():
                if not _sqlite_column_exists('episodes', column_name):
                    conn.execute(text(ddl))

    if 'qc_tasks' in existing_tables:
        qc_task_columns = {
            'version': 'ALTER TABLE qc_tasks ADD COLUMN version INTEGER NOT NULL DEFAULT 1',
            'lock_owner_user_id': "ALTER TABLE qc_tasks ADD COLUMN lock_owner_user_id VARCHAR(64) NOT NULL DEFAULT ''",
            'lock_owner_name': "ALTER TABLE qc_tasks ADD COLUMN lock_owner_name VARCHAR(64) NOT NULL DEFAULT ''",
            'lock_acquired_at': 'ALTER TABLE qc_tasks ADD COLUMN lock_acquired_at DATETIME',
            'lock_expires_at': 'ALTER TABLE qc_tasks ADD COLUMN lock_expires_at DATETIME',
        }
        with engine.begin() as conn:
            for column_name, ddl in qc_task_columns.items():
                if not _sqlite_column_exists('qc_tasks', column_name):
                    conn.execute(text(ddl))

    inspector = inspect(engine)
    episode_indexes = {item['name'] for item in inspector.get_indexes('episodes')} if 'episodes' in inspector.get_table_names() else set()
    with engine.begin() as conn:
        if 'episodes' in inspector.get_table_names() and 'ix_episodes_source_hash' not in episode_indexes:
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_episodes_source_hash ON episodes (source_hash)'))


def _alembic_config() -> Config:
    config = Config(str(BASE_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(BASE_DIR / 'migrations'))
    config.set_main_option('sqlalchemy.url', str(engine.url))
    return config


def _has_alembic_version_table() -> bool:
    inspector = inspect(engine)
    return 'alembic_version' in inspector.get_table_names()


def _has_business_tables() -> bool:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    business_tables = {
        'users',
        'task_types',
        'batches',
        'episodes',
        'qc_tasks',
        'qc_review_revisions',
        'audit_events',
        'ingest_jobs',
    }
    return bool(tables & business_tables)


def _ensure_migration_state() -> None:
    config = _alembic_config()
    if _has_alembic_version_table():
        command.upgrade(config, 'head')
        return
    if _has_business_tables():
        _sqlite_backfill_schema()
        command.stamp(config, 'head')
        return
    command.upgrade(config, 'head')


def initialize_schema() -> None:
    _ensure_sqlite_directory()
    _ensure_migration_state()


def initialize_admin(
    db: Session,
    *,
    username: str,
    password: str,
    name: str,
    role: str,
) -> User:
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        raise ValueError(f'user {username} already exists')

    user = User(
        id=f'user_{username}',
        username=username,
        name=name,
        role=role,
        avatar=(name or username or 'A')[:1].upper(),
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def initialize_database(*, admin_username: str, admin_password: str, admin_name: str = '系统管理员', admin_role: str = 'admin') -> User:
    initialize_schema()
    db = SessionLocal()
    try:
        return initialize_admin(
            db,
            username=admin_username,
            password=admin_password,
            name=admin_name,
            role=admin_role,
        )
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description='Initialize Robot QC database and create the first admin user.')
    parser.add_argument('--ensure-schema-only', action='store_true')
    parser.add_argument('--admin-username')
    parser.add_argument('--admin-password')
    parser.add_argument('--admin-name', default='系统管理员')
    parser.add_argument('--admin-role', default='admin')
    args = parser.parse_args()

    if args.ensure_schema_only:
        initialize_schema()
        print('Schema ensured successfully')
        return
    if not args.admin_username or not args.admin_password:
        raise SystemExit('--admin-username and --admin-password are required unless --ensure-schema-only is used')

    user = initialize_database(
        admin_username=args.admin_username,
        admin_password=args.admin_password,
        admin_name=args.admin_name,
        admin_role=args.admin_role,
    )
    print(f'Initialized database and created admin user: {user.username}')


if __name__ == '__main__':
    main()
