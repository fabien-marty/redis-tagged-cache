import uuid
from typing import Iterable, Optional

from rtc.app.metadata import MetadataPort


class BlackholeMetadataAdapter(MetadataPort):
    """Blackhole metadata adapter that does nothing."""

    def invalidate_tags(self, namespace: str, tag_names: Iterable[str]) -> None:
        return

    def get_or_set_tag_values(
        self, namespace: str, tag_names: Iterable[str], lifetime: Optional[int]
    ) -> Iterable[bytes]:
        return (uuid.uuid4().bytes for _ in tag_names)

    def lock(
        self,
        namespace: str,
        key: str,
        metadata_hash: str,
        timeout: int = 5,
        waiting: int = 1,
    ) -> Optional[str]:
        return uuid.uuid4().hex

    def unlock(
        self, namespace: str, key: str, metadata_hash: str, lock_identifier: str
    ) -> None:
        return
