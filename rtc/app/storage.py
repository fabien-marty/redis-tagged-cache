from abc import ABC, abstractmethod
from typing import List, Optional


class StoragePort(ABC):
    """Interface for the cache storage."""

    @abstractmethod
    def set(
        self, storage_key: str, value: bytes, lifetime: Optional[int] = None
    ) -> None:
        """Set a value under the given key for the given lifetime (in seconds).

        Note: lifetime = None means no expiration.

        """
        pass

    @abstractmethod
    def mget(self, storage_keys: List[str]) -> List[Optional[bytes]]:
        """Read multiple keys and return corresponding values.

        If a key does not exist, None is returned for the corresponding value.
        The returned list always has the same length than the keys list.

        """
        pass

    def get(self, storage_key: str) -> Optional[bytes]:
        """Read the value under the given key and return the value.

        If the key does not exist, None is returned.
        """
        return self.mget([storage_key])[0]

    @abstractmethod
    def delete(self, storage_key: str) -> None:
        """Delete the entry under the given key.

        Note: if the key does not exist, no exception is raised.

        """
        pass
