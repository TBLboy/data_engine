from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BASE_DIR.parents[1] if len(BASE_DIR.parents) > 1 else BASE_DIR
DEFAULT_SQLITE_PATH = BASE_DIR / 'data' / 'robot_qc.db'
BUG_REPORT_UPLOAD_DIR = BASE_DIR / 'data' / 'bug_reports'
DEFAULT_SECRET_KEY = 'robot-qc-dev-secret-change-in-prod'


class Settings(BaseSettings):
    app_name: str = 'Robot QC API'
    app_env: str = 'development'
    app_timezone: str = Field(default='Asia/Shanghai', alias='APP_TIMEZONE')
    api_prefix: str = '/api'
    host: str = '0.0.0.0'
    port: int = 8000
    frontend_origin: str = Field(default='http://localhost:5173', alias='FRONTEND_ORIGIN')
    extra_frontend_origins: str = Field(default='', alias='EXTRA_FRONTEND_ORIGINS')
    secret_key: str = Field(default=DEFAULT_SECRET_KEY, alias='SECRET_KEY')
    session_cookie_name: str = 'robot_qc_session'
    session_cookie_secure: bool = Field(default=False, alias='SESSION_COOKIE_SECURE')
    session_max_age_seconds: int = 60 * 60 * 12
    review_lock_ttl_seconds: int = Field(default=60 * 20, alias='REVIEW_LOCK_TTL_SECONDS')
    minio_endpoint: str = Field(default='127.0.0.1:9000', alias='MINIO_ENDPOINT')
    minio_access_key: str = Field(default='', alias='MINIO_ACCESS_KEY')
    minio_secret_key: str = Field(default='', alias='MINIO_SECRET_KEY')
    minio_secure: bool = Field(default=False, alias='MINIO_SECURE')
    minio_region: str = Field(default='', alias='MINIO_REGION')
    minio_default_bucket: str = Field(default='yaocao', alias='MINIO_DEFAULT_BUCKET')
    scan_cron_hour: int = Field(default=0, alias='SCAN_CRON_HOUR')
    scan_cron_minute: int = Field(default=0, alias='SCAN_CRON_MINUTE')
    scan_full_cron_day_of_week: str = Field(default='sun', alias='SCAN_FULL_CRON_DAY_OF_WEEK')
    scan_full_cron_hour: int = Field(default=2, alias='SCAN_FULL_CRON_HOUR')
    scan_full_cron_minute: int = Field(default=0, alias='SCAN_FULL_CRON_MINUTE')
    scan_coordinator_interval_seconds: int = Field(default=10, alias='SCAN_COORDINATOR_INTERVAL_SECONDS')
    scan_worker_poll_seconds: float = Field(default=2.0, alias='SCAN_WORKER_POLL_SECONDS')
    scan_worker_lease_seconds: int = Field(default=90, alias='SCAN_WORKER_LEASE_SECONDS')
    scan_worker_heartbeat_seconds: int = Field(default=10, alias='SCAN_WORKER_HEARTBEAT_SECONDS')
    scan_shard_timeout_seconds: int = Field(default=600, alias='SCAN_SHARD_TIMEOUT_SECONDS')
    scan_missing_confirmation_seconds: int = Field(default=600, alias='SCAN_MISSING_CONFIRMATION_SECONDS')
    data_assets_recompute_interval_seconds: int = Field(default=60, alias='DATA_ASSETS_RECOMPUTE_INTERVAL_SECONDS')
    data_assets_recompute_batch_limit: int = Field(default=100, alias='DATA_ASSETS_RECOMPUTE_BATCH_LIMIT')
    data_assets_reconcile_cron_hour: int = Field(default=3, alias='DATA_ASSETS_RECONCILE_CRON_HOUR')
    data_assets_reconcile_cron_minute: int = Field(default=30, alias='DATA_ASSETS_RECONCILE_CRON_MINUTE')
    # AI QC Explain
    ai_explain_enabled: bool = Field(default=False, alias='AI_EXPLAIN_ENABLED')
    ai_explain_provider: str = Field(default='ollama', alias='AI_EXPLAIN_PROVIDER')
    ollama_base_url: str = Field(default='http://localhost:11434', alias='OLLAMA_BASE_URL')
    ollama_model: str = Field(default='qwen2.5:7b', alias='OLLAMA_MODEL')
    ai_explain_timeout_seconds: int = Field(default=10, alias='AI_EXPLAIN_TIMEOUT_SECONDS')
    # Annotation VLM worker
    annotation_worker_poll_seconds: float = Field(default=2.0, alias='ANNOTATION_WORKER_POLL_SECONDS')
    annotation_worker_lease_seconds: int = Field(default=300, alias='ANNOTATION_WORKER_LEASE_SECONDS')
    annotation_worker_heartbeat_seconds: int = Field(default=15, alias='ANNOTATION_WORKER_HEARTBEAT_SECONDS')
    annotation_job_timeout_seconds: int = Field(default=900, alias='ANNOTATION_JOB_TIMEOUT_SECONDS')
    annotation_vlm_timeout_seconds: int = Field(default=300, alias='ANNOTATION_VLM_TIMEOUT_SECONDS')
    annotation_coordinator_interval_seconds: int = Field(default=60, alias='ANNOTATION_COORDINATOR_INTERVAL_SECONDS')
    # Auto VLM discovery (night window). Worker always drains queue regardless of window.
    annotation_discovery_enabled: bool = Field(default=True, alias='ANNOTATION_DISCOVERY_ENABLED')
    annotation_discovery_timezone: str = Field(default='Asia/Shanghai', alias='ANNOTATION_DISCOVERY_TIMEZONE')
    # Local wall-clock HH:MM inclusive start / exclusive end. Equal values = 24h open.
    annotation_discovery_window_start: str = Field(default='00:00', alias='ANNOTATION_DISCOVERY_WINDOW_START')
    annotation_discovery_window_end: str = Field(default='06:00', alias='ANNOTATION_DISCOVERY_WINDOW_END')
    # Max auto-created initial jobs per local calendar day (0 = unlimited within window).
    annotation_discovery_daily_limit: int = Field(default=100, alias='ANNOTATION_DISCOVERY_DAILY_LIMIT')
    database_url: str = Field(
        default=f'sqlite:///{DEFAULT_SQLITE_PATH}',
        alias='DATABASE_URL'
    )

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == 'production'

    @property
    def cors_allowed_origins(self) -> list[str]:
        origins = {
            self.frontend_origin,
            'http://127.0.0.1:5173',
            'http://localhost:5173',
        }
        extras = [item.strip() for item in self.extra_frontend_origins.split(',') if item.strip()]
        origins.update(extras)
        return sorted(origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
