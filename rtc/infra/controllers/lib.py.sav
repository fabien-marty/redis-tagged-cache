import logging
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, List, Optional, Union

from rtc.app.service import (
    DEFAULT_SERIALIZER,
    DEFAULT_UNSERIALIZER,
    CacheHook,
    CacheMiss,
    Service,
)
from rtc.app.storage import StoragePort
from rtc.infra.adapters.storage.blackhole import BlackHoleStorageAdapter
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
    _forced_adapter: Optional[StoragePort] = field(
        init=False, default=None
    )  # for unit-testing only
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
        adapter: StoragePort
        if self._forced_adapter:
            adapter = self._forced_adapter
        elif self.disabled:
            adapter = BlackHoleStorageAdapter()
        else:
            adapter = RedisStorageAdapter(
                redis_kwargs={
                    "host": self.host,
                    "port": self.port,
                    "db": self.db,
                    "ssl": self.ssl,
                    "socket_timeout": self.socket_timeout,
                    "socket_connect_timeout": self.socket_connect_timeout,
                }
            )
        return Service(
            storage_adapter=adapter,
            namespace=self.namespace,
            default_lifetime=self.default_lifetime,
            lifetime_for_tags=self.lifetime_for_tags,
            cache_hook=self.cache_hook,
        )

    def _serialize(self, value: Any) -> Optional[bytes]:
        try:
            return self.serializer(value)
        except Exception:
            logging.warning(
                "error when serializing provided data => cache bypassed",
                exc_info=True,
            )
            return None

    def _unserialize(self, value: bytes) -> Any:
        try:
            return self.unserializer(value)
        except Exception:
            logging.warning(
                "error when unserializing cached data => cache bypassed",
                exc_info=True,
            )
            raise

    def get(
        self,
        key: str,
        tags: Optional[List[str]] = None,
    ) -> Any:
        """Read the value for the given key (with given invalidation tags).

        If the key does not exist (or invalidated), None is returned.

        Raised:
            CacheMiss: if the key does not exist (or expired/invalidated).

        """
        tmp = self._service.get_value(key, tags or [])
        if tmp is None:
            raise CacheMiss()
        try:
            return self._unserialize(tmp)
        except Exception:
            return CacheMiss()

    def set(
        self,
        key: str,
        value: Any,
        tags: Optional[List[str]] = None,
        lifetime: Optional[int] = None,
    ) -> None:
        """Set a value for the given key (with given invalidation tags).

        Lifetime (in seconds) can be set (default to None: default expiration,
        0 means no expiration).

        """
        tmp = self._serialize(value)
        if tmp is not None:
            self._service.set_value(key, tmp, tags or [], lifetime)

    def delete(self, key: str, tags: Optional[List[str]] = None) -> None:
        """Delete the entry for the given key (with given invalidation tags).

        If the key does not exist (or invalidated), no exception is raised.

        """
        self._service.delete_value(key, tags or [])

    def invalidate(self, tags: Optional[Union[str, List[str]]] = None) -> None:
        """Invalidate entries with given tag/tags.

        Note: if tags is None, nothing is done.

        """
        if tags is None:
            return
        if isinstance(tags, str):
            self._service.invalidate_tags([tags])
        else:
            self._service.invalidate_tags(tags)

    def invalidate_all(self) -> None:
        """Invalidate all entries.

        Note: this is done by invalidating a special tag that is automatically used by all cache entries. So the complexity is still O(1).

        """
        self._service.invalidate_all()

    def function_decorator(
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
        return self._service.decorator(
            tags,
            lifetime=lifetime,
            key=key,
            hook_userdata=hook_userdata,
            serializer=serializer if serializer else self.serializer,
            unserializer=unserializer if unserializer else self.unserializer,
            lock=lock,
            lock_timeout=lock_timeout,
        )

    def method_decorator(
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
        """Decorator for caching the result of a method.

        Notes:

        - for functions, you should use `function_decorator` instead (because with `method_decorator` the first argument is ignored in automatic key generation)
        - the result of the method must be pickleable
        - `tags` and `lifetime` are the same as for `set` method (but `tags` can also be a callable here to provide dynamic tags)
        - `key` is an optional method that can be used to generate a custom key
        - `hook_userdata` is an optional variable that can be transmitted to custom cache hooks (useless else)
        - if `serializer` or `unserializer` are not provided, we will use the serializer/unserializer defined passed in the `RedisTaggedCache` constructor
        - `lock` is an optional boolean to enable a lock mechanism to avoid cache stampede (default to False), there is some overhead but can
        be interesting for slow functions
        - `lock_timeout` is an optional integer to set the lock timeout in seconds (default to 5), should be greater that the time
        needed to call the decorated function

        If you don't provide a `key` argument, a key is automatically generated from the method name/location and its calling arguments (they must be JSON serializable).
        You can override this behavior by providing a custom `key` function with following signature:

        ```python
        def custom_key(*args, **kwargs) -> str:
            # {your code here to generate key}
            # make your own key from *args, **kwargs that are exactly the calling arguments of the decorated method (including self)
            return key
        ```

        If you are interested by settings dynamic tags (i.e. tags that are computed at runtime depending on the method calling arguments), you can provide a callable for `tags` argument
        with the following signature:

        ```python
        def dynamic_tags(*args, **kwargs) -> List[str]:
            # {your code here to generate tags}
            # make your own tags from *args, **kwargs that are exactly the calling arguments of the decorated method (including self)
            return tags

        ```

        """
        return self._service.decorator(
            tags,
            lifetime=lifetime,
            key=key,
            ignore_first_argument=True,
            hook_userdata=hook_userdata,
            serializer=serializer if serializer else DEFAULT_SERIALIZER,
            unserializer=unserializer if unserializer else DEFAULT_UNSERIALIZER,
            lock=lock,
            lock_timeout=lock_timeout,
        )
