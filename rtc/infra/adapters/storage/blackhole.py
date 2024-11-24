from dataclasses import dataclass
from typing import List, Optional

from rtc.app.storage import StoragePort


@dataclass
class BlackHoleStorageAdapter(StoragePort):
    """BlackHole storage adapter that stores nothing.

    Note: used when disabled=True in the main controller.

    """

    def set(
        self, storage_key: str, value: bytes, lifetime: Optional[int] = None
    ) -> None:
        pass

    def get(self, storage_key: str) -> Optional[bytes]:
        return None

    def delete(self, storage_key: str) -> None:
        pass

    def mget(self, storage_keys: List[str]) -> List[Optional[bytes]]:
        return [None] * len(storage_keys)
