import base64
import zlib
from typing import Union


def _hash(data: Union[str, bytes]) -> int:
    """Generate a hash of the given string or bytes.

    This is a simple hash function that uses the zlib library.
    It is not a cryptographic hash function, but it is fast and suitable for our use case.

    Returns:
        A 32-bit (non signed) integer hash of the given data.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    return zlib.adler32(data) & 0xFFFFFFFF


def short_hash(data: Union[str, bytes]) -> str:
    """Generate a text hash of the given string or bytes.

    This is a simple hash function that uses the zlib library.
    It is not a cryptographic hash function, but it is fast and suitable for our use case.

    Returns:
        A base64 encoded string (url variant) of the hash (without padding and with ~ instead of -)
    """
    h = _hash(data)
    return (
        base64.urlsafe_b64encode(h.to_bytes(4, "big"))
        .decode("utf-8")
        .rstrip("=")
        .replace("-", "~")
    )
