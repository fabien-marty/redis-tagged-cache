from dataclasses import dataclass
from typing import Optional

from rtc.app.storage import StoragePort


@dataclass
class BlackHoleStorageAdapter(StoragePort):
    """BlackHole storage adapter that stores nothing.

    Note: used when disabled=True in the main controller.

    """

    def set(
        self, namespace: str, key: str, metadata_hash: str, value: bytes, lifetime: int
    ) -> None:
        pass

    def get(self, namespace: str, key: str, metadata_hash: str) -> Optional[bytes]:
        return None

    def delete(self, namespace: str, key: str, metadata_hash: str) -> bool:
        return False
