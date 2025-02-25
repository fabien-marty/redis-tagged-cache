import datetime
import time
import uuid
from dataclasses import dataclass, field
from threading import Lock, Thread
import wrapt
from typing import Dict, Iterable, List, Optional, Tuple

from rtc.app.metadata import MetadataPort
from rtc.app.storage import StoragePort


class LockWithId:
    _lock: Lock
    _id: Optional[str] = None

    def __init__(self):
        self._lock = Lock()
        self._id = None

    def acquire(self, wait_timeout: int) -> Optional[str]:
        acquired = self._lock.acquire(blocking=True, timeout=wait_timeout)
        if acquired:
            self._id = str(uuid.uuid4())
            return self._id
        return None

    def release(self):
        self._id = None
        try:
            self._lock.release()
        except RuntimeError:
            pass


@dataclass
class MonitoredLock:
    lock: LockWithId
    timeout: int

    _expiration: Optional[datetime.datetime] = None

    def __post_init__(self):
        self._expiration = datetime.datetime.now() + datetime.timedelta(
            seconds=self.timeout
        )

    @property
    def is_expired(self) -> bool:
        assert self._expiration is not None
        return datetime.datetime.now() > self._expiration

    def auto_release(self) -> bool:
        if not self.is_expired:
            return False
        try:
            self.lock.release()
        except RuntimeError:
            pass
        return True


class AutoExpirationThread:
    _singleton: Optional["AutoExpirationThread"] = None
    _singleton_lock: Lock = Lock()

    _internal_lock: Lock
    _monitored_locks: Dict[str, MonitoredLock]
    _thread: Optional[Thread]

    def __init__(self):
        self._internal_lock = Lock()
        self._monitored_locks = {}
        self._thread = None

    def monitor(self, lock: LockWithId, lock_timeout: int):
        with self._internal_lock:
            lock_id = lock._id
            assert lock_id is not None
            self._monitored_locks[lock_id] = MonitoredLock(
                lock=lock, timeout=lock_timeout
            )
            if self._thread is None:
                self._thread = Thread(target=self.run, daemon=True)
                self._thread.start()

    def unmonitor(self, lock_id: str):
        with self._internal_lock:
            try:
                self._monitored_locks.pop(lock_id)
            except Exception:
                pass

    def run(self):
        while True:
            with self._internal_lock:
                if len(self._monitored_locks) == 0:
                    self._thread = None
                    return
                self._monitored_locks = {
                    lock_id: lock
                    for lock_id, lock in self._monitored_locks.items()
                    if not lock.auto_release()
                }
            time.sleep(1)

    @classmethod
    def get_or_make(cls) -> "AutoExpirationThread":
        with cls._singleton_lock:
            if cls._singleton is None:
                cls._singleton = cls()
            return cls._singleton


class Item:
    value: Optional[bytes]
    _expiration: Optional[datetime.datetime]
    _lock: LockWithId

    def __init__(
        self,
        value: Optional[bytes],
        expiration_lifetime: Optional[int] = None,
    ):
        self.value = value
        if expiration_lifetime is not None:
            self._expiration = datetime.datetime.now() + datetime.timedelta(
                seconds=expiration_lifetime
            )
        else:
            self._expiration = None
        self._lock = LockWithId()

    def update(
        self, new_value: Optional[bytes], new_expiration_lifetime: Optional[int] = None
    ):
        self.value = new_value
        if new_expiration_lifetime is not None:
            self._expiration = datetime.datetime.now() + datetime.timedelta(
                seconds=new_expiration_lifetime
            )

    def acquire(self, wait_timeout: int, lock_timeout: int) -> Optional[str]:
        self._lock_id = self._lock.acquire(wait_timeout)
        if self._lock_id:
            AutoExpirationThread.get_or_make().monitor(self._lock, lock_timeout)
        return self._lock_id

    def release(self, lock_id: str):
        AutoExpirationThread.get_or_make().unmonitor(lock_id)
        try:
            self._lock.release()
        except RuntimeError:
            pass

    @property
    def is_expired(self) -> bool:
        if self._expiration is None:
            return False
        return datetime.datetime.now() > self._expiration


@wrapt.decorator
def locked(wrapped, instance, args, kwargs):
    with instance._lock:
        return wrapped(*args, **kwargs)


@dataclass
class DictMetadataAdapter(MetadataPort):
    _internal_lock: Lock = field(init=False, repr=False, default_factory=Lock)
    _tags: Dict[Tuple[str, str], bytes] = field(
        default_factory=dict
    )  # (namespace, tag_name) -> value
    _locks: Dict[Tuple[str, str], LockWithId] = field(default_factory=dict)
    _content: Dict[str, Item] = field(default_factory=dict)

    @locked
    def invalidate_tags(self, namespace: str, tag_names: Iterable[str]) -> None:
        for tag_name in tag_names:
            self._tags[(namespace, tag_name)] = uuid.uuid4().bytes

    @locked
    def get_or_set_tag_values(
        self, namespace: str, tag_names: Iterable[str], lifetime: Optional[int]
    ) -> Iterable[bytes]:
        for tag_name in tag_names:
            value = self._tags.get((namespace, tag_name))
            if value is None:
                value = uuid.uuid4().bytes
                self._tags[(namespace, tag_name)] = value
            yield value

    def lock(
        self,
        namespace: str,
        key: str,
        metadata_hash: str,
        timeout: int = 5,
        waiting: int = 1,
    ) -> Optional[str]:
        return uuid.uuid4().hex

    def unlock(
        self, namespace: str, key: str, metadata_hash: str, lock_identifier: str
    ) -> None:
        return
