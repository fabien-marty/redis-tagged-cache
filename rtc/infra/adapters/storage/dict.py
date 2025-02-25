import threading
from dataclasses import dataclass, field
import time
from typing import Dict, Optional, Tuple

import wrapt

from rtc.app.storage import StoragePort


@wrapt.decorator
def locked(wrapped, instance, args, kwargs):
    with instance._lock:
        return wrapped(*args, **kwargs)


class Item:
    value: bytes
    _expiration: Optional[float] = None

    def __init__(
        self,
        value: bytes,
        expiration_lifetime: Optional[int] = None,
    ):
        self.value = value
        if expiration_lifetime is not None:
            self._expiration = time.perf_counter() + expiration_lifetime
        else:
            self._expiration = None

    def update(self, new_value: bytes):
        self.value = new_value
        self._expiration = (
            time.perf_counter()
            + new_expirdatetime.datetime.now()
            + datetime.timedelta(seconds=new_expiration_lifetime)
        )

    @property
    def is_expired(self) -> bool:
        if self._expiration is None:
            return False
        return time.perf_counter() > self._expiration


@dataclass
class DictStorageAdapter(StoragePort):
    _data: Dict[Tuple[str, str], Item] = field(
        default_factory=dict
    )  # (namespace, key) -> value
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @locked
    def set(
        self, namespace: str, key: str, metadata_hash: str, value: bytes, lifetime: int
    ) -> None:
        self._data[(namespace, key)] = Item(value, lifetime)

    @locked
    def get(self, namespace: str, key: str, metadata_hash: str) -> Optional[bytes]:
        item = self._data.get((namespace, key))
        if item is None:
            return None
        if item.is_expired:
            self._delete(namespace, key, metadata_hash)
        return item.value

    def _delete(self, namespace: str, key: str, metadata_hash: str) -> bool:
        try:
            self._data.pop((namespace, key))
            return True
        except KeyError:
            return False

    @locked
    def delete(self, namespace: str, key: str, metadata_hash: str) -> bool:
        return self._delete(namespace, key, metadata_hash)
