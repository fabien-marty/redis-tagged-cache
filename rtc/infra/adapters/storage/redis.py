import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import redis

from rtc.app.exc import StorageCacheException
from rtc.app.hash import short_hash
from rtc.app.storage import StoragePort


def get_storage_key(namespace: str, key: str, metadata_hash: str) -> str:
    return f"rtc:{short_hash(namespace)}:s:{short_hash(key)}:{metadata_hash}"


@dataclass
class RedisStorageAdapter(StoragePort):
    """Redis adapter for the storage port."""

    redis_kwargs: Dict[str, Any] = field(default_factory=dict)
    _redis_client: Optional[redis.Redis] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def redis_client(self) -> redis.Redis:
        with self._lock:
            if self._redis_client is None:
                self._redis_client = redis.Redis(**self.redis_kwargs)
            return self._redis_client

    def set(
        self, namespace: str, key: str, metadata_hash: str, value: bytes, lifetime: int
    ) -> None:
        storage_key = get_storage_key(namespace, key, metadata_hash)
        try:
            if lifetime:
                self.redis_client.set(storage_key, value, ex=lifetime)
            else:
                self.redis_client.set(storage_key, value)
        except Exception as e:
            raise StorageCacheException(f"Failed to set value in Redis: {e}") from e

    def get(self, namespace: str, key: str, metadata_hash: str) -> Optional[bytes]:
        storage_key = get_storage_key(namespace, key, metadata_hash)
        try:
            return self.redis_client.get(storage_key)  # type: ignore
        except Exception as e:
            raise StorageCacheException(f"Failed to get value from Redis: {e}") from e

    def delete(self, namespace: str, key: str, metadata_hash: str) -> bool:
        storage_key = get_storage_key(namespace, key, metadata_hash)
        try:
            deleted = self.redis_client.delete(storage_key)
            return deleted > 0  # type: ignore
        except Exception as e:
            raise StorageCacheException(
                f"Failed to delete value from Redis: {e}"
            ) from e
