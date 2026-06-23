from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BASE_DIR.parents[1] if len(BASE_DIR.parents) > 1 else BASE_DIR
DEFAULT_SQLITE_PATH = BASE_DIR / 'data' / 'robot_qc.db'
DEFAULT_SAMPLE_PROCESSED_ROOT = PROJECT_ROOT / 'data' / 'raw' / 'process'
if not DEFAULT_SAMPLE_PROCESSED_ROOT.exists():
    DEFAULT_SAMPLE_PROCESSED_ROOT = BASE_DIR / 'data' / 'raw' / 'process'
DEFAULT_SECRET_KEY = 'robot-qc-dev-secret-change-in-prod'


class Settings(BaseSettings):
    app_name: str = 'Robot QC API'
    app_env: str = 'development'
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
    collection_data_root: Path = Field(default=Path('/data/collection_data'), alias='COLLECTION_DATA_ROOT')
    sample_processed_root: Path = Field(default=DEFAULT_SAMPLE_PROCESSED_ROOT, alias='SAMPLE_PROCESSED_ROOT')
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
