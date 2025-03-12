from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Iterable, Optional, Union

from rtc.app.decorator import cache_decorator
from rtc.app.metadata import MetadataPort, MetadataService
from rtc.app.serializer import DEFAULT_SERIALIZER, DEFAULT_UNSERIALIZER
from rtc.app.service import Service
from rtc.app.storage import StoragePort, StorageService
from rtc.app.types import (
    CacheHook,
)
from rtc.infra.adapters.metadata.blackhole import BlackHoleMetadataAdapter
from rtc.infra.adapters.metadata.dict import DictMetadataAdapter
from rtc.infra.adapters.metadata.redis import RedisMetadataAdapter
from rtc.infra.adapters.storage.blackhole import BlackHoleStorageAdapter
from rtc.infra.adapters.storage.dict import DictStorageAdapter
from rtc.infra.adapters.storage.redis import RedisStorageAdapter


@dataclass
class RedisTaggedCache:
    """A Redis-based caching system with tag-based invalidation support.

    This class provides a thread-safe caching implementation using Redis as the backend.
    It supports tag-based cache invalidation, allowing you to invalidate multiple cache
    entries at once by invalidating their associated tags.

    Features:
    - Thread-safe operations
    - Tag-based cache invalidation
    - Configurable cache entry lifetimes
    - Local memory cache option for testing
    - Automatic and customizable serialization support
    - Decorator interface for easy function result caching
    - Cache hooks for monitoring and debugging

    Example:
        ```python
        cache = RedisTaggedCache(
            host="localhost",
            port=6379
        )

        # Basic usage
        cache.set("key", "value", tags=["tag1", "tag2"])
        assert cache.get("key") == "value"
        cache.invalidate("tag1")  # Invalidates all entries with tag1

        cache.get("key")  # it will raise a CacheMiss exception
        ```

    Note:
        All operations are thread-safe and can be used in multi-threaded environments.
    """

    namespace: str = "default"
    """Namespace prefix for all cache entries to avoid key collisions."""

    host: str = "localhost"
    """Redis server hostname or IP address."""

    port: int = 6379
    """Redis server port number."""

    db: int = 0
    """Redis database number (0-15)."""

    ssl: bool = False
    """Whether to use SSL/TLS for Redis connection."""

    socket_timeout: int = 5
    """Socket timeout in seconds for Redis operations."""

    socket_connect_timeout: int = 5
    """Socket connection timeout in seconds when establishing Redis connection."""

    default_lifetime: Optional[int] = 3600  # 1h
    """Default lifetime for cache entries in seconds.

    If set to None, entries will not expire automatically. In this case, ensure your
    Redis instance is configured with an appropriate eviction policy.
    """

    lifetime_for_tags: Optional[int] = 86400  # 24h
    """Lifetime for tag entries in seconds.

    When a tag expires or is invalidated, all cache entries associated with that tag
    are also invalidated. Set to None for no automatic tag expiration.
    """

    disabled: bool = False
    """If True, disables all caching operations while maintaining the API interface.

    Useful for testing or temporarily disabling cache without code changes.
    """

    in_local_memory: bool = False
    """If True, uses process-local memory instead of Redis for storage.

    Warning:
        This mode is intended for testing only and should not be used in production
        as it doesn't provide cross-process cache consistency.
    """

    cache_hook: Optional[CacheHook] = None
    """Optional callback function for monitoring cache operations.

    The hook function is called after each cache decorator operation with the following signature:
    ```python
    def cache_hook(
        key: str,
        tags: Iterable[str],
        cache_info: CacheInfo,
        userdata: Optional[Any] = None
    ) -> None:
        pass
    ```

    Parameters:
        - key: The cache key being accessed
        - tags: Iterable of tags associated with the key
        - cache_info: Object containing cache operation metrics
        - userdata: Optional custom data passed through the decorator
    """

    serializer: Callable[[Any], Optional[bytes]] = DEFAULT_SERIALIZER
    """Function to serialize Python objects before storing in cache.

    Must accept any Python object and return bytes or None (means: cache bypassed).
    """

    unserializer: Callable[[bytes], Any] = DEFAULT_UNSERIALIZER
    """Function to deserialize data read from cache back into Python objects.

    Must accept bytes and return the original Python object.
    """

    _internal_lock: Lock = field(init=False, default_factory=Lock)
    _forced_metadata_adapter: Optional[MetadataPort] = field(
        init=False, default=None
    )  # for advanced usage only
    _forced_storage_adapter: Optional[StoragePort] = field(
        init=False, default=None
    )  # for advanced usage only
    __service: Optional[Service] = field(
        init=False, default=None
    )  # cache of the Service object

    @property
    def _service(self) -> Service:
        with self._internal_lock:
            if self.__service is None:
                self.__service = self._make_service()
            return self.__service

    def _make_service(self) -> Service:
        metadata_adapter: MetadataPort
        storage_adapter: StoragePort
        redis_kwargs = {
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "ssl": self.ssl,
            "socket_timeout": self.socket_timeout,
            "socket_connect_timeout": self.socket_connect_timeout,
        }
        if self._forced_metadata_adapter:
            metadata_adapter = self._forced_metadata_adapter
        elif self.disabled:
            metadata_adapter = BlackHoleMetadataAdapter()
        elif self.in_local_memory:
            metadata_adapter = DictMetadataAdapter()
        else:
            metadata_adapter = RedisMetadataAdapter(redis_kwargs)
        if self._forced_storage_adapter:
            storage_adapter = self._forced_storage_adapter
        elif self.disabled:
            storage_adapter = BlackHoleStorageAdapter()
        elif self.in_local_memory:
            storage_adapter = DictStorageAdapter()
        else:
            storage_adapter = RedisStorageAdapter(redis_kwargs)
        return Service(
            namespace=self.namespace,
            metadata_service=MetadataService(
                namespace=self.namespace,
                adapter=metadata_adapter,
                default_lifetime=self.lifetime_for_tags or 0,
            ),
            storage_service=StorageService(
                namespace=self.namespace,
                adapter=storage_adapter,
                default_lifetime=self.default_lifetime or 0,
            ),
            cache_hook=self.cache_hook,
            serializer=self.serializer,
            unserializer=self.unserializer,
        )

    def _rebuild_service(self):
        with self._internal_lock:
            self.__service = None

    def set(
        self,
        key: str,
        value: Any,
        tags: Optional[Iterable[str]] = None,
        lifetime: Optional[int] = None,
    ) -> bool:
        """Store a value in the cache with optional tags and lifetime.

        Args:
            key: Unique identifier for the cache entry
            value: Any Python object to store (must be serializable)
            tags: Optional list of tags for invalidation
            lifetime: Optional TTL in seconds (if set: overrides default_lifetime, 0 means no expiration)

        Returns:
            bool: True if the value was successfully stored, False otherwise

        Example:
            ```python
            cache.set("user:123", user_data, tags=["user", "user:123"], lifetime=3600)
            ```
        """
        return self._service.set(key, value, tags, lifetime)

    def delete(self, key: str, tags: Optional[Iterable[str]] = None) -> bool:
        """Remove an entry from the cache.

        Args:
            key: The key to delete
            tags: Optional list of tags (for consistency, should match set() tags)

        Returns:
            bool: True if the key was found and deleted, False if it didn't exist

        Note:
            No exception is raised if the key doesn't exist or was already invalidated.
        """
        return self._service.delete(key, tags)

    def get(
        self,
        key: str,
        tags: Optional[Iterable[str]] = None,
    ) -> Any:
        """Retrieve a value from the cache.

        Args:
            key: The key to look up
            tags: Optional list of tags (for consistency, should match set() tags)

        Returns:
            The stored value if found and valid

        Raises:
            CacheMiss: If the key doesn't exist, has expired, or was invalidated

        Example:
            ```python
            try:
                value = cache.get("user:123", tags=["user", "user:123"])
            except CacheMiss:
                value = compute_user_data()
            ```
        """
        return self._service.get(key, tags)

    def invalidate(self, tags: Union[str, Iterable[str]]) -> bool:
        """Invalidate all cache entries associated with the given tag(s).

        Args:
            tags: Single tag string or iterable of tags to invalidate

        Returns:
            bool: True if the invalidation was successful

        Example:
            ```python
            # Invalidate all user-related cache entries
            cache.invalidate("user")

            # Invalidate multiple tags at once
            cache.invalidate(["user:123", "session:456"])
            ```
        """
        if isinstance(tags, str):
            return self._service.invalidate_tags([tags])
        else:
            return self._service.invalidate_tags(tags)

    def invalidate_all(self) -> bool:
        """Invalidate all cache entries in the current namespace.

        This operation is implemented efficiently using a special tag that is
        automatically associated with all cache entries. The operation is O(1)
        regardless of the number of cache entries.

        Returns:
            bool: True if the invalidation was successful

        Example:
            ```python
            # Clear entire cache (within current namespace)
            cache.invalidate_all()
            ```
        """
        return self._service.invalidate_all()

    def decorator(
        self,
        tags: Optional[Union[Iterable[str], Callable[..., Iterable[str]]]] = None,
        lifetime: Optional[int] = None,
        key: Optional[Callable[..., str]] = None,
        hook_userdata: Optional[Any] = None,
        lock: bool = False,
        lock_timeout: int = 5,
        serializer: Optional[Callable[[Any], Optional[bytes]]] = None,
        unserializer: Optional[Callable[[bytes], Any]] = None,
    ) -> Callable:
        """Decorator for automatically caching function results.

        This decorator provides a high-level interface for caching function return values.
        It supports both static and dynamic cache keys and tags, custom serialization,
        and protection against cache stampede.

        If you don't provide a key, we will generate a key from the function name and arguments
        (that must be JSON-serializable). For methods, we will use the method name and class name
        but the instance (self) won't be taken into account by default (for generating the key).

        Args:
            tags: Static list of tags or a function that generates tags dynamically
            lifetime: Optional TTL in seconds (overrides default_lifetime)
            key: Optional function to generate custom cache keys
            hook_userdata: Optional data passed to cache hooks
            lock: If True, uses distributed locking to prevent cache stampede
            lock_timeout: Lock timeout in seconds (default: 5)
            serializer: Optional custom serializer for this function
            unserializer: Optional custom unserializer for this function

        Returns:
            A decorator function that can be applied to methods or functions

        Example:
            ```python
            # Basic usage with static tags
            @cache.decorator(tags=["user"])
            def get_user(user_id: int) -> dict:
                return db.fetch_user(user_id)

            # Dynamic tags based on function arguments
            @cache.decorator(
                tags=lambda user_id: [f"user:{user_id}", "user"],
                lifetime=3600
            )
            def get_user_with_dynamic_tags(user_id: int) -> dict:
                return db.fetch_user(user_id)

            # Custom cache key generation
            @cache.decorator(
                key=lambda user_id: f"user_profile:{user_id}"
            )
            def get_user_profile(user_id: int) -> dict:
                return db.fetch_user_profile(user_id)

            # Protection against cache stampede
            @cache.decorator(lock=True, lock_timeout=10)
            def expensive_computation() -> dict:
                return perform_slow_calculation()
            ```

        Note:
            - The decorated function's arguments must be JSON-serializable for automatic key generation
            - When using custom key functions, ensure keys are unique and deterministic
            - Lock timeout should be greater than the expected function execution time
        """
        return cache_decorator(
            service=self._service,
            serializer=serializer if serializer else self.serializer,
            unserializer=unserializer if unserializer else self.unserializer,
            lock=lock,
            lock_timeout=lock_timeout,
            key=key,
            hook_userdata=hook_userdata,
            tags=tags,
            lifetime=lifetime,
        )

    def function_decorator(self, *args, **kwargs):
        """DEPRECATED: Use `decorator()` instead.

        This method will be removed in a future version.
        """
        return self.decorator(*args, **kwargs)

    def method_decorator(self, *args, **kwargs):
        """DEPRECATED: Use `decorator()` instead.

        This method will be removed in a future version.
        """
        return self.decorator(*args, **kwargs)
