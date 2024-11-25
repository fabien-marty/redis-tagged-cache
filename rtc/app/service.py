import base64
import hashlib
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Union

from rtc.app.storage import StoragePort

SPECIAL_ALL_TAG_NAME = "@@@all@@@"


def short_hash(data: Union[str, bytes]) -> str:
    """Generate a short alpha-numeric hash of the given string or bytes."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    h = hashlib.sha256(data).digest()[0:8]
    return (
        base64.b64encode(h)
        .decode("utf-8")
        .replace("=", "")
        .replace("+", "-")
        .replace("/", "_")
    )


@dataclass
class Service:
    storage_adapter: StoragePort
    namespace: str = "default"
    default_lifetime: Optional[int] = None
    lifetime_for_tags: Optional[int] = None

    namespace_hash: str = field(init=False, default="")

    def __post_init__(self):
        self.namespace_hash = short_hash(self.namespace)

    def resolve_lifetime(self, lifetime: Optional[int]) -> Optional[int]:
        """Resolve the given lifetime with the default value.

        If the given value is not None => return it. Else return the default value
        set at the instance level.

        """
        if lifetime is not None:
            return lifetime
        return self.default_lifetime

    def get_storage_tag_key(self, tag_name: str) -> str:
        """Compute and return the storage_key for the given tag name."""
        tag_name_hash = short_hash(tag_name)
        return f"rtc:{self.namespace_hash}:t:{tag_name_hash}"

    def _invalidate_tag(self, storage_tag_key: str) -> bytes:
        """Invalidate the tag (given its storage_tag_key).

        The new tag uuid value is returned.

        """
        new_value = short_hash(uuid.uuid4().bytes).encode("utf-8")
        self.storage_adapter.set(
            storage_tag_key, new_value, lifetime=self.lifetime_for_tags
        )
        return new_value

    def get_tag_values(self, tag_names: List[str]) -> List[bytes]:
        """Returns tag values (as a list) for a list of tag names.

        If a tag does not exist (aka does not have a value), a value is generated
        and returned.

        """
        res: List[bytes] = []
        tag_storage_keys = [
            self.get_storage_tag_key(tag_name) for tag_name in tag_names
        ]
        values = self.storage_adapter.mget(tag_storage_keys)
        for tag_storage_key, value in zip(tag_storage_keys, values):
            if value is None:
                # First use of this tag! Let's generate a fist value
                # Yes, there is a race condition here, but it's not a big problem
                # (maybe we are going to invalidate the tag twice)
                res.append(self._invalidate_tag(tag_storage_key))
            else:
                res.append(value)
        return res

    def get_storage_value_key(self, value_key: str, tag_names: List[str]) -> str:
        """Compute and return the storage_key for the given value_key (and tag names)."""
        special_tag_names = tag_names[:]
        if SPECIAL_ALL_TAG_NAME not in tag_names:
            special_tag_names.append(SPECIAL_ALL_TAG_NAME)
        tags_values = self.get_tag_values(special_tag_names)
        tags_hash = short_hash(b"".join(tags_values))
        value_key_hash = short_hash(value_key)
        return f"rtc:{self.namespace_hash}:v:{value_key_hash}:{tags_hash}"

    def invalidate_tag(self, tag_name: str) -> None:
        """Invalidate a tag given its name."""
        tag_storage_key = self.get_storage_tag_key(tag_name)
        self._invalidate_tag(tag_storage_key)

    def invalidate_tags(self, tag_names: List[str]) -> None:
        """Invalidate a list of tag names."""
        for tag_name in tag_names:
            self.invalidate_tag(tag_name)

    def invalidate_all(self) -> None:
        """Invalidate all entries."""
        self.invalidate_tag(SPECIAL_ALL_TAG_NAME)

    def set_value(
        self,
        key: str,
        value: bytes,
        tag_names: List[str],
        lifetime: Optional[int] = None,
    ) -> None:
        """Set a value for the given key (with given invalidation tags).

        Lifetime can be set (default to 0: no expiration)

        """
        storage_key = self.get_storage_value_key(key, tag_names)
        resolved_lifetime = self.resolve_lifetime(lifetime)
        self.storage_adapter.set(storage_key, value, lifetime=resolved_lifetime)

    def get_value(self, key: str, tags: List[str]) -> Optional[bytes]:
        """Read the value for the given key (with given invalidation tags).

        If the key does not exist (or invalidated), None is returned.

        """
        storage_key = self.get_storage_value_key(key, tags)
        return self.storage_adapter.mget([storage_key])[0]

    def delete_value(self, key: str, tags: List[str]) -> None:
        """Delete the entry for the given key (with given invalidation tags).

        If the key does not exist (or invalidated), no exception is raised.

        """
        storage_key = self.get_storage_value_key(key, tags)
        self.storage_adapter.delete(storage_key)
