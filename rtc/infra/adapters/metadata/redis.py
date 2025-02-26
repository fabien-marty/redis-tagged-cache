import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

import redis

from rtc.app.exc import MetadataCacheException
from rtc.app.hash import get_random_bytes, short_hash
from rtc.app.metadata import MetadataPort

LOCK_LUA_SCRIPT = """
if redis.call("get",KEYS[1]) == ARGV[1]
then
    return redis.call("del",KEYS[1])
else
    return 0
end
"""


def get_tag_key(namespace: str, tag_name: str) -> str:
    return f"rtc:{short_hash(namespace)}:t:{short_hash(tag_name)}"


def get_lock_key(namespace: str, key: str, metadata_hash: str) -> str:
    return f"rtc:{short_hash(namespace)}:l:{short_hash(key)}:{metadata_hash}"


def get_waiting_key(namespace: str, key: str, metadata_hash: str) -> str:
    return f"rtc:{short_hash(namespace)}:w:{short_hash(key)}:{metadata_hash}"


@dataclass
class RedisMetadataAdapter(MetadataPort):
    """Redis adapter for the metadata port."""

    redis_kwargs: Dict[str, Any] = field(default_factory=dict)
    _redis_client: Optional[redis.Redis] = None
    _redis_client_lock: threading.Lock = field(default_factory=threading.Lock)
    _redis_lock_del_cmd: Any = field(default=None, init=False, repr=False)
    _redis_lock_del_cmd_lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def redis_client(self) -> redis.Redis:
        with self._redis_client_lock:
            if self._redis_client is None:
                self._redis_client = redis.Redis(**self.redis_kwargs)
            return self._redis_client

    @property
    def redis_lock_del_cmd(self) -> Any:
        with self._redis_lock_del_cmd_lock:
            if self._redis_lock_del_cmd is None:
                self._redis_lock_del_cmd = self.redis_client.register_script(
                    LOCK_LUA_SCRIPT
                )
            return self._redis_lock_del_cmd

    def get_or_set_tag_values(
        self, namespace: str, tag_names: Iterable[str], lifetime: Optional[int]
    ) -> Iterable[bytes]:
        tag_keys = [get_tag_key(namespace, tag_name) for tag_name in tag_names]
        try:
            values: List[bytes] = self.redis_client.mget(tag_keys)  # type: ignore
        except Exception as e:
            raise MetadataCacheException(
                f"Failed to get tag values from Redis: {e}"
            ) from e
        empty_tag_keys = [
            (i, tag_key)
            for i, (tag_key, value) in enumerate(zip(tag_keys, values))
            if value is None
        ]
        for i, _ in empty_tag_keys:
            values[i] = get_random_bytes()
        if empty_tag_keys:
            try:
                self.redis_client.mset({key: values[i] for i, key in empty_tag_keys})
            except Exception as e:
                raise MetadataCacheException(
                    f"Failed to set tag values in Redis: {e}"
                ) from e
        return values

    def invalidate_tags(self, namespace: str, tag_names: Iterable[str]) -> None:
        tag_keys = [get_tag_key(namespace, tag_name) for tag_name in tag_names]
        try:
            self.redis_client.mset({key: get_random_bytes() for key in tag_keys})
        except Exception as e:
            raise MetadataCacheException(
                f"Failed to set tag values in Redis: {e}"
            ) from e

    def lock(
        self,
        namespace: str,
        key: str,
        metadata_hash: str,
        timeout: int = 5,
        waiting: int = 1,
    ) -> Optional[str]:
        lock_id = get_random_bytes().hex()
        lock_storage_key = get_lock_key(namespace, key, metadata_hash)
        lock_waiting_key = get_waiting_key(namespace, key, metadata_hash)
        before = time.perf_counter()
        while (time.perf_counter() - before) < waiting:
            try:
                res = self.redis_client.set(
                    lock_storage_key, lock_id, ex=timeout, nx=True
                )
                if res is not None:
                    # we have the lock
                    return lock_id
                # lock is already taken
                # => let's wait unlock() to be called (or up to 1s)
                self.redis_client.blpop([lock_waiting_key], timeout=1)
            except Exception as e:
                raise MetadataCacheException(
                    f"Failed to lock tag values in Redis: {e}"
                ) from e
        return None

    def unlock(
        self, namespace: str, key: str, metadata_hash: str, lock_identifier: str
    ) -> None:
        lock_storage_key = get_lock_key(namespace, key, metadata_hash)
        lock_waiting_key = get_waiting_key(namespace, key, metadata_hash)
        try:
            pipe = self.redis_client.pipeline(transaction=True)
            self.redis_lock_del_cmd(
                keys=[lock_storage_key],
                args=[lock_identifier],
                client=pipe,
            )
            pipe.rpush(lock_waiting_key, "x")
            pipe.expire(lock_waiting_key, time=3)
            pipe.execute()
        except Exception as e:
            raise MetadataCacheException(
                f"Failed to unlock tag values in Redis: {e}"
            ) from e
