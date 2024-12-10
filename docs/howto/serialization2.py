from typing import Any

from rtc import RedisTaggedCache


def custom_serializer(value: Any) -> bytes:
    """Custom serializer is a simple function to convert any value to bytes.

    Here, we consider that value is already bytes.

    If an exception is raised here, a warning will be logged
    and the cache will be bypassed.

    """
    try:
        value.decode()
    except (AttributeError, UnicodeDecodeError):
        raise TypeError("The value must be bytes")
    # value is bytes
    return value  # type: ignore


cache = RedisTaggedCache(
    namespace="foo",
    host="localhost",
    port=6379,
    serializer=custom_serializer,
    unserializer=lambda x: x,  # we don't need any transformation in that particular case
)

# Use cache normally
value_as_bytes = b"foo"
cache.set("key1", value_as_bytes, tags=["tag1", "tag2"])
