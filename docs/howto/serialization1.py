import pickle
import zlib
from typing import Any

from rtc import RedisTaggedCache


def custom_serializer(value: Any) -> bytes:
    """Custom serializer is a simple function to convert any value to bytes.

    If an exception is raised here, a warning will be logged
    and the cache will be bypassed.

    """
    serialized = pickle.dumps(value)  # serialize the value
    return zlib.compress(serialized)  # compress the serialized value


def custom_unserializer(value: bytes) -> Any:
    """Custom unserializer is a simple function to convert bytes to a value.

    If an exception is raised here, a warning will be logged
    and the cache will be bypassed.

    """
    serialized = zlib.decompress(value)  # decompress the value
    return pickle.loads(serialized)  # unserialize the value


cache = RedisTaggedCache(
    namespace="foo",
    host="localhost",
    port=6379,
    serializer=custom_serializer,
    unserializer=custom_unserializer,
)

# Use cache normally
value = ["data", "to", "store"]
cache.set("key1", value, tags=["tag1", "tag2"])
