from typing import Iterable, Optional

from rtc.app.hash import get_random_bytes
from rtc.app.metadata import MetadataPort


class BlackHoleMetadataAdapter(MetadataPort):
    """Blackhole metadata adapter that does nothing."""

    def invalidate_tags(self, namespace: str, tag_names: Iterable[str]) -> None:
        return

    def get_or_set_tag_values(
        self, namespace: str, tag_names: Iterable[str], lifetime: Optional[int]
    ) -> Iterable[bytes]:
        return (get_random_bytes() for _ in tag_names)

    def lock(
        self,
        namespace: str,
        key: str,
        metadata_hash: str,
        timeout: int = 5,
        waiting: int = 1,
    ) -> Optional[str]:
        return get_random_bytes().hex()

    def unlock(
        self, namespace: str, key: str, metadata_hash: str, lock_identifier: str
    ) -> None:
        return
