from __future__ import annotations

from functools import lru_cache
from datetime import timedelta

from minio import Minio
import urllib3
from urllib3.util import Retry, Timeout

from app.core.config import get_settings


class MinioService:
    def __init__(self) -> None:
        settings = get_settings()
        http_client = urllib3.PoolManager(
            timeout=Timeout(connect=5, read=60),
            maxsize=10,
            retries=Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504]),
        )
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            region=settings.minio_region or None,
            http_client=http_client,
        )

    def list_objects(self, bucket: str, prefix: str = '', *, recursive: bool = True):
        return self._client.list_objects(bucket, prefix=prefix, recursive=recursive)

    def presigned_get_object(self, bucket: str, object_key: str, *, expires: timedelta):
        return self._client.presigned_get_object(bucket, object_key, expires=expires)

    def get_object(self, bucket: str, object_key: str):
        return self._client.get_object(bucket, object_key)


@lru_cache
def get_minio_service() -> MinioService:
    return MinioService()
