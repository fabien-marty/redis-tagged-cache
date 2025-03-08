from dataclasses import dataclass
from typing import Optional

from rtc.app.exc import StorageCacheException
from rtc.infra.adapters.storage.blackhole import BlackHoleStorageAdapter


@dataclass
class BadStorageAdapter(BlackHoleStorageAdapter):
    """Bad storage adapter that does not work.

    If the fail property is True (default), it raises an exception for every operation.

    It's only for unit-testing.

    """

    fail: bool = True

    def set(
        self, namespace: str, key: str, metadata_hash: str, value: bytes, lifetime: int
    ) -> None:
        if self.fail:
            raise StorageCacheException("Bad storage adapter")
        return super().set(namespace, key, metadata_hash, value, lifetime)

    def get(self, namespace: str, key: str, metadata_hash: str) -> Optional[bytes]:
        if self.fail:
            raise StorageCacheException("Bad storage adapter")
        return super().get(namespace, key, metadata_hash)

    def delete(self, namespace: str, key: str, metadata_hash: str) -> bool:
        if self.fail:
            raise StorageCacheException("Bad storage adapter")
        return super().delete(namespace, key, metadata_hash)
