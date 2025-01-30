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
    def mdelete(self, storage_keys: List[str]) -> None:
        """Delete entries under the given keys.

        Note: if a key does not exist, no exception is raised.

        """
        pass

    def delete(self, storage_keys: str) -> None:
        """Delete the entry under the given key.

        Note: if the key does not exist, no exception is raised.

        """
        return self.mdelete([storage_keys])

    @abstractmethod
    def lock(
        self, storage_key: str, timeout: int = 5, waiting: int = 1
    ) -> Optional[str]:
        """Lock the entry under the given key.

        The lock is live until unlock() call or the lock is expired (after timeout seconds).

        This call is blocking (up to waiting seconds) until the lock is acquired.

        If None is returned, the lock could not be acquired in the waiting delay.
        Otherwise, the lock is acquired and a unique lock identifier is returned.

        """
        pass

    @abstractmethod
    def unlock(self, storage_key: str, lock_identifier: str) -> None:
        """Unlock the entry under the given key.

        The lock_identifier is the one returned by the lock method.

        """
        pass
