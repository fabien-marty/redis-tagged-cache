import itertools
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable, Optional

from rtc.app.hash import short_hash

SPECIAL_ALL_TAG_NAME = "@@@all@@@"

DEFAULT_LIFETIME = 604800  # Default lifetime (in seconds)


class MetadataPort(ABC):
    """Interface for the metadata port."""

    @abstractmethod
    def invalidate_tags(self, namespace: str, tag_names: Iterable[str]) -> None:
        """Invalidate the given tags.

        Note: if a tag does not exist, it is ignored.

        Args:
            namespace: the namespace.
            tag_names: the names of the tags to invalidate.

        """
        pass

    @abstractmethod
    def get_or_set_tag_values(
        self, namespace: str, tag_names: Iterable[str], lifetime: Optional[int]
    ) -> Iterable[bytes]:
        """Get the (unique/random) values of the given tags.

        If a tag does not exist, it is created with a random value.

        Args:
            namespace: the namespace.
            tag_names: the names of the tags.
            lifetime: the lifetime of the tag (in seconds), None means "no expiration".

        Returns:
            The (unique/random) values of the given tags (same order than the tag names).

        """
        pass

    @abstractmethod
    def lock(
        self,
        namespace: str,
        key: str,
        metadata_hash: str,
        timeout: int = 5,
        waiting: int = 1,
    ) -> Optional[str]:
        """Lock the entry under the given key.

        The lock is live until unlock() call or the lock is expired (after timeout seconds).

        This call is blocking (up to waiting seconds) until the lock is acquired.

        If None is returned, the lock could not be acquired in the waiting delay.
        Otherwise, the lock is acquired and a unique lock identifier is returned.

        """
        pass

    @abstractmethod
    def unlock(
        self, namespace: str, key: str, metadata_hash: str, lock_identifier: str
    ) -> None:
        """Unlock the entry under the given key.

        The lock_identifier is the one returned by the lock method.

        Note: if the lock is not found, this call is a no-op.

        """
        pass


def get_logger() -> logging.Logger:
    return logging.getLogger("rtc.app.metadata")


@dataclass
class MetadataService:
    namespace: str
    adapter: MetadataPort
    lifetime: int = DEFAULT_LIFETIME
    logger: logging.Logger = field(default_factory=get_logger)

    def invalidate_tags(self, tag_names: Iterable[str]) -> None:
        self.logger.debug("Invalidating tags: %s", ", ".join(tag_names))
        return self.adapter.invalidate_tags(self.namespace, tag_names)

    def invalidate_all(self) -> None:
        self.logger.debug("Invalidating all cache")
        return self.adapter.invalidate_tags(self.namespace, (SPECIAL_ALL_TAG_NAME,))

    def get_metadata_hash(self, tag_names: Iterable[str]) -> str:
        sorted_tag_names = sorted(itertools.chain(tag_names, (SPECIAL_ALL_TAG_NAME,)))
        tags_values = self.adapter.get_or_set_tag_values(
            self.namespace, sorted_tag_names, self.lifetime
        )
        return short_hash(b" ".join(tags_values))

    def lock(self, key: str, metadata_hash: str, timeout: int = 5, waiting: int = 1):
        return self.adapter.lock(self.namespace, key, metadata_hash, timeout, waiting)

    def unlock(self, key: str, metadata_hash: str, lock_identifier: str) -> None:
        return self.adapter.unlock(self.namespace, key, metadata_hash, lock_identifier)
