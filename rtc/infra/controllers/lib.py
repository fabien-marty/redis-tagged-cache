from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Iterable, List, Optional, Union

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
    """Main class for Redis-based tagged cache.


    Note: thread-safe.

    """

    namespace: str = "default"
    """Namespace for the cache entries."""

    host: str = "localhost"
    """Redis server hostname."""

    port: int = 6379
    """Redis server port."""

    db: int = 0
    """Redis database number."""

    ssl: bool = False
    """Use SSL for the connection."""

    socket_timeout: int = 5
    """Socket timeout in seconds."""

    socket_connect_timeout: int = 5
    """Socket connection timeout in seconds."""

    default_lifetime: Optional[int] = 3600  # 1h
    """Default lifetime for cache entries (in seconds).

    Note: None means "no expiration" (be sure in that case that your redis is
    configured to automatically evict keys even if they are not volatile).

    """

    lifetime_for_tags: Optional[int] = 86400  # 24h
    """Lifetime for tags entries (in seconds).

    If a tag used by a cache entry is invalidated, the cache entry is also invalidated.

    Note: None means "no expiration" (be sure in that case that your redis is
    configured to automatically evict keys even if they are not volatile).

    """

    disabled: bool = False
    """If True, the cache is disabled (cache always missed and no write) but the API is still available."""

    in_local_memory: bool = False
    """If True, the cache is stored in the process local memory (no redis at all!).

    This mode is NOT production ready and have some major caveats! You should use it
    only for unit-testing.

    """

    cache_hook: Optional[CacheHook] = None
    """Optional custom hook called after each cache decorator usage.

    Note: the hook is called with the key, the list of tags, a CacheInfo object containing
    interesting metrics / internal values and an optional userdata variable
    (set with `hook_userdata` parameter of decorator methods).

    The signature of the hook must be:

    ```python
    def your_hook(key: str, tags: List[str], cache_info: CacheInfo, userdata: Optional[Any] = None) -> None:
        # {your code here}
        return
    ```

    """

    serializer: Callable[[Any], Optional[bytes]] = DEFAULT_SERIALIZER
    """Serializer function to serialize data before storing it in the cache."""

    unserializer: Callable[[bytes], Any] = DEFAULT_UNSERIALIZER
    """Unserializer function to unserialize data after reading it from the cache."""

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
                lifetime=self.lifetime_for_tags or 0,
            ),
            storage_service=StorageService(
                namespace=self.namespace,
                adapter=storage_adapter,
                default_lifetime=self.default_lifetime or 0,
            ),
            cache_hook=self.cache_hook,
        )

    def set(
        self,
        key: str,
        value: Any,
        tags: Optional[Iterable[str]] = None,
        lifetime: Optional[int] = None,
    ) -> bool:
        """Set a value for the given key (with given invalidation tags).

        Lifetime (in seconds) can be set (default to None: default expiration,
        0 means no expiration).

        """
        return self._service.set(key, value, tags, lifetime)

    def delete(self, key: str, tags: Optional[Iterable[str]] = None) -> bool:
        """Delete the entry for the given key (with given invalidation tags).

        If the key does not exist (or invalidated), no exception is raised.

        """
        return self._service.delete(key, tags)

    def get(
        self,
        key: str,
        tags: Optional[Iterable[str]] = None,
    ) -> Any:
        """Read the value for the given key (with given invalidation tags).

        If the key does not exist (or invalidated), None is returned.

        Raised:
            CacheMiss: if the key does not exist (or expired/invalidated).

        """
        return self._service.get(key, tags)

    def invalidate(self, tags: Union[str, Iterable[str]]) -> bool:
        """Invalidate entries with given tag/tags."""
        return self._service.invalidate_tags(tags)

    def invalidate_all(self) -> bool:
        """Invalidate all entries.

        Note: this is done by invalidating a special tag that is automatically used by all cache entries. So the complexity is still O(1).

        """
        return self._service.invalidate_all()

    def decorator(
        self,
        tags: Optional[Union[List[str], Callable[..., List[str]]]] = None,
        lifetime: Optional[int] = None,
        key: Optional[Callable[..., str]] = None,
        hook_userdata: Optional[Any] = None,
        lock: bool = False,
        lock_timeout: int = 5,
        serializer: Optional[Callable[[Any], Optional[bytes]]] = None,
        unserializer: Optional[Callable[[bytes], Any]] = None,
    ):
        """Decorator for caching the result of a function.

        Notes:

        - for method, you should use `method_decorator` instead (because with `method_decorator` the first argument `self` is ignored in automatic key generation)
        - the result of the function must be pickleable
        - `tags` and `lifetime` are the same as for `set` method (but `tags` can also be a callable here to provide dynamic tags)
        - `key` is an optional function that can be used to generate a custom key
        - `hook_userdata` is an optional variable that can be transmitted to custom cache hooks (useless else)
        - if `serializer` or `unserializer` are not provided, we will use the serializer/unserializer defined passed in the `RedisTaggedCache` constructor
        - `lock` is an optional boolean to enable a lock mechanism to avoid cache stampede (default to False), there is some overhead but can
        be interesting for slow functions
        - `lock_timeout` is an optional integer to set the lock timeout in seconds (default to 5), should be greater that the time
        needed to call the decorated function

        If you don't provide a `key` argument, a key is automatically generated from the function name/location and its calling arguments (they must be JSON serializable).
        You can override this behavior by providing a custom `key` function with following signature:

        ```python
        def custom_key(*args, **kwargs) -> str:
            # {your code here to generate key}
            # make your own key from *args, **kwargs that are exactly the calling arguments of the decorated function
            return key
        ```

        If you are interested by settings dynamic tags (i.e. tags that are computed at runtime depending on the function calling arguments), you can provide a callable for `tags` argument
        with the following signature:

        ```python
        def dynamic_tags(*args, **kwargs) -> List[str]:
            # {your code here to generate tags}
            # make your own tags from *args, **kwargs that are exactly the calling arguments of the decorated function
            return tags
        ```

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
        """DEPRECATED => USE `decorator()` instead."""
        return self.decorator(*args, **kwargs)

    def method_decorator(self, *args, **kwargs):
        """DEPRECATED => USE `decorator()` instead."""
        return self.decorator(*args, **kwargs)
