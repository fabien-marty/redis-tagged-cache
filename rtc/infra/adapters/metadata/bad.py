from dataclasses import dataclass
from typing import Iterable, Optional

from rtc.app.exc import MetadataCacheException
from rtc.infra.adapters.metadata.blackhole import BlackHoleMetadataAdapter


@dataclass
class BadMetadataAdapter(BlackHoleMetadataAdapter):
    """Bad metadata adapter that does not work.

    If the fail property is True (default), it raises an exception for every operation.

    It's only for unit-testing.

    """

    fail: bool = True

    def invalidate_tags(
        self, namespace: str, tag_names: Iterable[str], lifetime: Optional[int]
    ) -> None:
        if self.fail:
            raise MetadataCacheException("Bad metadata adapter")
        return super().invalidate_tags(namespace, tag_names, lifetime)

    def get_or_set_tag_values(
        self, namespace: str, tag_names: Iterable[str], lifetime: Optional[int]
    ) -> Iterable[bytes]:
        if self.fail:
            raise MetadataCacheException("Bad metadata adapter")
        return super().get_or_set_tag_values(namespace, tag_names, lifetime)

    def lock(
        self,
        namespace: str,
        key: str,
        metadata_hash: str,
        timeout: int = 5,
        waiting: int = 1,
    ) -> Optional[str]:
        if self.fail:
            raise MetadataCacheException("Bad metadata adapter")
        return super().lock(namespace, key, metadata_hash, timeout, waiting)

    def unlock(
        self, namespace: str, key: str, metadata_hash: str, lock_identifier: str
    ) -> None:
        if self.fail:
            raise MetadataCacheException("Bad metadata adapter")
        return super().unlock(namespace, key, metadata_hash, lock_identifier)
