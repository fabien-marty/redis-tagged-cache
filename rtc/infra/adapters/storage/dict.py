import datetime
import time
import uuid
from dataclasses import dataclass, field
from threading import Lock, Thread
from typing import Dict, List, Optional

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


@dataclass
class DictStorageAdapter(StoragePort):
    """Dummy storage adapter that stores data in a Python dict.

    Note: only for unit-testing!

    """

    _internal_lock: Lock = field(init=False, repr=False, default_factory=Lock)
    _content: Dict[str, Item] = field(default_factory=dict)

    def _set(
        self,
        storage_key: str,
        value: Optional[bytes],
        lifetime: Optional[int] = None,
    ) -> Item:
        item = self._content.get(storage_key)
        if item is None:
            item = Item(value=value, expiration_lifetime=lifetime)
            self._content[storage_key] = item
        else:
            item.update(value, lifetime)
        return item

    def set(
        self, storage_key: str, value: bytes, lifetime: Optional[int] = None
    ) -> None:
        with self._internal_lock:
            self._set(storage_key, value, lifetime)

    def _get(self, storage_key: str) -> Optional[Item]:
        item = self._content.get(storage_key)
        if item is None:
            return None
        if item.is_expired:
            self._set(storage_key, None)
            return None
        return item

    def get(self, storage_key: str) -> Optional[bytes]:
        with self._internal_lock:
            item = self._get(storage_key)
            if item is None:
                return None
            return item.value

    def mdelete(self, storage_keys: List[str]) -> None:
        with self._internal_lock:
            for storage_key in storage_keys:
                try:
                    self._content.pop(storage_key, None)
                except KeyError:
                    pass

    def mget(self, storage_keys: List[str]) -> List[Optional[bytes]]:
        return [self.get(k) for k in storage_keys]

    def lock(
        self, storage_key: str, timeout: int = 5, waiting: int = 1
    ) -> Optional[str]:
        with self._internal_lock:
            item = self._get(storage_key)
            if item is None:
                item = self._set(storage_key, value=None, lifetime=None)
        lock_id = item.acquire(wait_timeout=waiting, lock_timeout=timeout)
        if lock_id:
            # acquired
            return lock_id
        # not acquired
        return None

    def unlock(self, storage_key: str, lock_id: str) -> None:
        with self._internal_lock:
            item = self._get(storage_key)
        if item is None:
            return
        try:
            item.release(lock_id)
        except RuntimeError:
            pass
