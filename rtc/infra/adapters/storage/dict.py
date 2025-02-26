import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import wrapt

from rtc.app.storage import StoragePort


@wrapt.decorator
def locked(wrapped, instance, args, kwargs):
    with instance._internal_lock:
        return wrapped(*args, **kwargs)


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
class DictStorageAdapter(StoragePort):
    _data: Dict[Tuple[str, str, str], Item] = field(
        default_factory=dict
    )  # (namespace, key, metadata_hash) -> value
    _internal_lock: threading.Lock = field(default_factory=threading.Lock)

    @locked
    def set(
        self, namespace: str, key: str, metadata_hash: str, value: bytes, lifetime: int
    ) -> None:
        self._data[(namespace, key, metadata_hash)] = Item(value, lifetime)

    @locked
    def get(self, namespace: str, key: str, metadata_hash: str) -> Optional[bytes]:
        item = self._data.get((namespace, key, metadata_hash))
        if item is None:
            return None
        if item.is_expired:
            self._delete(namespace, key, metadata_hash)
            return None
        return item.value

    def _delete(self, namespace: str, key: str, metadata_hash: str) -> bool:
        try:
            self._data.pop((namespace, key, metadata_hash))
            return True
        except KeyError:
            return False

    @locked
    def delete(self, namespace: str, key: str, metadata_hash: str) -> bool:
        return self._delete(namespace, key, metadata_hash)
