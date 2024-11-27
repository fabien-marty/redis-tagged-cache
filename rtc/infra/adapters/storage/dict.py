import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from rtc.app.storage import StoragePort


@dataclass
class Item:
    value: bytes
    expiration_timestamp: Optional[float] = None

    @property
    def is_expired(self) -> bool:
        if self.expiration_timestamp is None:
            return False
        return self.expiration_timestamp < int(time.time())


@dataclass
class DictStorageAdapter(StoragePort):
    """Dummy storage adapter that stores data in a Python dict.

    Note: only for unit-testing!

    """

    _content: Dict[str, Item] = field(default_factory=dict)

    def _get_expiration_lifetime(self, lifetime: Optional[int]) -> Optional[float]:
        if lifetime is not None:
            return time.time() + lifetime
        return None

    def set(
        self, storage_key: str, value: bytes, lifetime: Optional[int] = None
    ) -> None:
        expiration_timestamp = self._get_expiration_lifetime(lifetime)
        self._content[storage_key] = Item(
            value=value, expiration_timestamp=expiration_timestamp
        )

    def get(self, storage_key: str) -> Optional[bytes]:
        item = self._content.get(storage_key)
        if item is None:
            return None
        if item.is_expired:
            self._content.pop(storage_key, None)
            return None
        return item.value

    def mdelete(self, storage_keys: List[str]) -> None:
        for storage_key in storage_keys:
            self._content.pop(storage_key, None)

    def mget(self, storage_keys: List[str]) -> List[Optional[bytes]]:
        return [self.get(k) for k in storage_keys]
