import time
from dataclasses import dataclass, field
from threading import Lock, Thread
from typing import Dict, Iterable, Optional, Tuple

import wrapt

from rtc.app.hash import get_random_bytes
from rtc.app.metadata import MetadataPort


@wrapt.decorator
def locked(wrapped, instance, args, kwargs):
    with instance._internal_lock:
        return wrapped(*args, **kwargs)


class LockWithId:
    _lock: Lock
    _id: Optional[str]
    _expiration: float

    def __init__(self, lifetime: int):
        self._lock = Lock()
        self._id = None
        self._expiration = time.perf_counter() + lifetime

    def acquire(self, wait_timeout: int) -> Optional[str]:
        acquired = self._lock.acquire(blocking=True, timeout=wait_timeout)
        if acquired:
            self._id = get_random_bytes().hex()
            return self._id
        return None

    def release(self):
        self._id = None
        try:
            self._lock.release()
        except RuntimeError:
            pass

    @property
    def is_expired(self) -> bool:
        return time.perf_counter() > self._expiration


@dataclass
class Item:
    value: bytes
    lifetime: int
    _expiration: float = field(default=0.0)

    def __post_init__(self):
        if self.lifetime > 0:
            self._expiration = time.perf_counter() + self.lifetime

    @property
    def is_expired(self) -> bool:
        if self._expiration < 0.1:
            return False
        return time.perf_counter() > self._expiration


@dataclass
class DictMetadataAdapter(MetadataPort):
    _internal_lock: Lock = field(init=False, repr=False, default_factory=Lock)
    _tags: Dict[Tuple[str, str], Item] = field(
        default_factory=dict
    )  # (namespace, tag_name) -> value
    _locks: Dict[Tuple[str, str, str], LockWithId] = field(
        default_factory=dict
    )  # (namespace, key, metadata_hash) -> LockWithId
    _expiration_thread: Optional[Thread] = None

    def __post_init__(self):
        self._expiration_thread = Thread(target=self.expiration_thread_run, daemon=True)
        self._expiration_thread.start()

    @locked
    def invalidate_tags(
        self, namespace: str, tag_names: Iterable[str], lifetime: Optional[int]
    ) -> None:
        for tag_name in tag_names:
            print("invalidate_tags", namespace, tag_name)
            self._tags[(namespace, tag_name)] = Item(
                value=get_random_bytes(), lifetime=lifetime or 0
            )

    @locked
    def get_or_set_tag_values(
        self, namespace: str, tag_names: Iterable[str], lifetime: Optional[int]
    ) -> Iterable[bytes]:
        for tag_name in tag_names:
            item = self._tags.get((namespace, tag_name))
            if item is None:
                new_value = get_random_bytes()
                self._tags[(namespace, tag_name)] = Item(
                    value=new_value, lifetime=lifetime or 0
                )
                yield new_value
            else:
                yield item.value

    def lock(
        self,
        namespace: str,
        key: str,
        metadata_hash: str,
        timeout: int = 5,
        waiting: int = 1,
    ) -> Optional[str]:
        with self._internal_lock:
            lock_with_id = self._locks.get((namespace, key, metadata_hash))
            if lock_with_id is None:
                lock_with_id = LockWithId(timeout)
                self._locks[(namespace, key, metadata_hash)] = lock_with_id
                return lock_with_id.acquire(waiting)  # Can't block
        return lock_with_id.acquire(waiting)

    def unlock(
        self, namespace: str, key: str, metadata_hash: str, lock_identifier: str
    ) -> None:
        with self._internal_lock:
            try:
                lock_with_id = self._locks.pop((namespace, key, metadata_hash))
            except KeyError:
                return
            lock_with_id.release()

    def expiration_thread_run(self):
        while True:
            with self._internal_lock:
                new_locks: Dict[Tuple[str, str, str], LockWithId] = {}
                for k, lock_with_id in self._locks.items():
                    if lock_with_id.is_expired:
                        lock_with_id.release()
                    else:
                        new_locks[k] = lock_with_id
                self._locks = new_locks
            time.sleep(0.5)
