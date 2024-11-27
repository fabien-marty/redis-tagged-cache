import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import redis

from rtc.app.storage import StoragePort


@dataclass
class RedisStorageAdapter(StoragePort):
    """Redis adapter for the storage port."""

    redis_kwargs: Dict[str, Any] = field(default_factory=dict)

    @property
    def redis_client(self) -> redis.Redis:
        return redis.Redis(**self.redis_kwargs)

    def set(
        self, storage_key: str, value: bytes, lifetime: Optional[int] = None
    ) -> None:
        try:
            self.redis_client.set(storage_key, value, ex=lifetime)
        except Exception:
            logging.warning("Failed to set value in Redis", exc_info=True)

    def mdelete(self, storage_keys: List[str]) -> None:
        try:
            self.redis_client.delete(*storage_keys)
        except Exception:
            logging.warning("Failed to delete values in Redis", exc_info=True)

    def mget(self, storage_keys: List[str]) -> List[Optional[bytes]]:
        try:
            return self.redis_client.mget(storage_keys)  # type: ignore
        except Exception:
            logging.warning("Failed to mget values in Redis", exc_info=True)
            return [None] * len(storage_keys)
