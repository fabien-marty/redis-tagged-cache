class CacheMiss(Exception):
    """Exception raised when a cache miss occurs."""

    pass


class CacheException(Exception):
    """Base exception for cache-related errors."""

    pass


class MetadataCacheException(CacheException):
    """Exception raised when a metadata cache error occurs."""

    pass


class StorageCacheException(CacheException):
    """Exception raised when a storage cache error occurs."""

    pass
