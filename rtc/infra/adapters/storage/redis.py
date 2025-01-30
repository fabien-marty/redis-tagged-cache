import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import redis
import redis.commands

from rtc.app.storage import StoragePort

LOCK_LUA_SCRIPT = """
if redis.call("get",KEYS[1]) == ARGV[1]
then
    return redis.call("del",KEYS[1])
else
    return 0
end
"""


@dataclass
class RedisStorageAdapter(StoragePort):
    """Redis adapter for the storage port."""

    redis_kwargs: Dict[str, Any] = field(default_factory=dict)
    _redis_client: Optional[redis.Redis] = None
    _redis_lock_del_cmd: Any = field(init=False, repr=False)

    @property
    def redis_client(self) -> redis.Redis:
        if self._redis_client is None:
            self._redis_client = redis.Redis(**self.redis_kwargs)
            self._redis_lock_del_cmd = self._redis_client.register_script(
                LOCK_LUA_SCRIPT
            )
        return self._redis_client

    @property
    def redis_lock_del_cmd(self) -> Any:
        if self._redis_lock_del_cmd is None:
            _ = self.redis_client
            assert self._redis_lock_del_cmd is not None
        return self._redis_lock_del_cmd

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

    def get_lock_storage_key(self, storage_key: str) -> str:
        return f"{storage_key}:lock"

    def get_lock_waiting_key(self, storage_key: str) -> str:
        return f"{storage_key}:waiting"

    def lock(
        self, storage_key: str, timeout: int = 5, waiting: int = 1
    ) -> Optional[str]:
        lock_id = str(uuid.uuid4())
        lock_storage_key = self.get_lock_storage_key(storage_key)
        lock_waiting_key = self.get_lock_waiting_key(storage_key)
        before = time.perf_counter()
        while (time.perf_counter() - before) < waiting:
            res = self.redis_client.set(lock_storage_key, lock_id, ex=timeout, nx=True)
            if res is not None:
                # we have the lock
                return lock_id
            # lock is already taken
            # => let's wait a unlock() was called or wait up to 1s
            self.redis_client.blpop([lock_waiting_key], timeout=1)
        return None

    def unlock(self, storage_key: str, lock_identifier: str) -> None:
        lock_storage_key = self.get_lock_storage_key(storage_key)
        lock_waiting_key = self.get_lock_waiting_key(storage_key)
        pipe = self.redis_client.pipeline(transaction=True)
        self._redis_lock_del_cmd(
            keys=[lock_storage_key],
            args=[lock_identifier],
            client=pipe,
        )
        pipe.rpush(lock_waiting_key, "x")
        pipe.expire(lock_waiting_key, time=3)
        pipe.execute()
