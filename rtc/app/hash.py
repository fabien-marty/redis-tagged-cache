import base64
import hashlib
import uuid
from typing import Union

HASH_SIZE_IN_BYTES = 8


def _hash(data: Union[str, bytes]) -> bytes:
    """Generate a hash of the given string or bytes."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.md5(data).digest()


def short_hash(data: Union[str, bytes]) -> str:
    """Generate a short text hash of the given string or bytes.

    It is not a cryptographic hash function, but it is fast and suitable for our use case.
    You can configure the hash size in bytes in the HASH_SIZE_IN_BYTES constant.

    Returns:
        A base64 encoded string (url variant) of the hash (without padding and with ~ instead of -)
    """
    h = _hash(data)[0:HASH_SIZE_IN_BYTES]
    return base64.urlsafe_b64encode(h).decode("utf-8").rstrip("=").replace("-", "~")


def get_random_bytes() -> bytes:
    """Generate a random bytes string.

    Note: you can use .hex() on the result to get a random string.

    """
    return uuid.uuid4().bytes
