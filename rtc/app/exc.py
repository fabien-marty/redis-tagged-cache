class CacheMiss(Exception):
    """Exception raised when a cache miss occurs."""

    pass


class CacheException(Exception):
    pass


class MetadataCacheException(CacheException):
    pass


class StorageCacheException(CacheException):
    pass
