import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_LIFETIME = 86400  # Default lifetime (in seconds)


class StoragePort(ABC):
    """Interface for the cache storage."""

    @abstractmethod
    def set(
        self,
        namespace: str,
        key: str,
        metadata_hash: str,
        value: bytes,
        lifetime: int,
    ) -> None:
        """Set a value under the given key for the given lifetime (in seconds).

        Note: <=0 means "no expiration"

        Raises:
            StorageException: if we can't store the value.

        """
        pass

    @abstractmethod
    def get(self, namespace: str, key: str, metadata_hash: str) -> Optional[bytes]:
        """Read the value under the given key and return the value.

        If the key does not exist, None is returned.

        Raises:
            StorageException: if we had an excepted error (not if the key does not exist).

        """
        pass

    @abstractmethod
    def delete(self, namespace: str, key: str, metadata_hash: str) -> bool:
        """Delete the entry under the given key.

        Note: if the key does not exist, no exception is raised.

        Returns:
            true if we really deleted something.

        Raises:
            StorageException: if we had an excepted error (not if the key does not exist).

        """
        pass


def get_logger() -> logging.Logger:
    return logging.getLogger("rtc.app.storage")


@dataclass
class StorageService:
    namespace: str
    adapter: StoragePort
    default_lifetime: int = DEFAULT_LIFETIME
    logger: logging.Logger = field(default_factory=get_logger)

    def _resolve_lifetime(self, lifetime: Optional[int]) -> int:
        """Resolve the given lifetime with the default value.

        If the given value is not None => return it. Else return the default value
        set at the instance level.

        """
        if lifetime is not None:
            return lifetime
        return self.default_lifetime

    def set(
        self, key: str, metadata_hash: str, value: bytes, lifetime: Optional[int] = None
    ) -> None:
        self.logger.debug(
            "Setting value for key: %s (metadata_hash: %s)", key, metadata_hash
        )
        self.adapter.set(
            self.namespace,
            key,
            metadata_hash,
            value,
            self._resolve_lifetime(lifetime),
        )

    def get(self, key: str, metadata_hash: str) -> Optional[bytes]:
        self.logger.debug(
            "Getting value for key: %s (metadata_hash: %s)", key, metadata_hash
        )
        return self.adapter.get(self.namespace, key, metadata_hash)

    def delete(self, key: str, metadata_hash: str) -> bool:
        self.logger.debug("Deleting value for key: %s", key)
        return self.adapter.delete(self.namespace, key, metadata_hash)
