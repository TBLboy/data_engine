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
