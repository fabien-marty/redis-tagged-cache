import logging
import pickle
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Union

from rtc.app.service import CacheHook, CacheMiss, Service
from rtc.app.storage import StoragePort
from rtc.infra.adapters.storage.blackhole import BlackHoleStorageAdapter
from rtc.infra.adapters.storage.redis import RedisStorageAdapter


@dataclass
class RedisTaggedCache:
    """Main class for Redis-based tagged cache."""

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

    log_cache_hit: bool = True
    """If True, log cache hits with standard logging with a debug message."""

    log_cache_miss: bool = True
    """If True, log cache miss with standard logging with a debug message."""

    cache_hit_hook: Optional[CacheHook] = None
    """Optional custom hook called when a cache hit occurs.

    Note: the hook is called with the key, the list of tags and an optional userdata variable
    (set with `hook_userdata` parameter of `get`/decorators method).

    The signature of the hook must be:

    ```python
    def your_hook(key: str, tags: List[str], userdata: Optional[Any]) -> None:
        # {your code here}
        return
    ```

    """

    cache_miss_hook: Optional[CacheHook] = None
    """Optional custom hook called when a cache miss occurs.

    Note: the hook is called with the key, the list of tags and an optional userdata variable
    (set with `hook_userdata` parameter of `get`/decorators method).

    The signature of the hook must be:

    ```python
    def your_hook(key: str, tags: List[str], userdata: Optional[Any]) -> None:
        # {your code here}
        return
    ```

    """

    serializer: Callable[[Any], bytes] = pickle.dumps
    """Serializer function to serialize data before storing it in the cache."""

    unserializer: Callable[[bytes], Any] = pickle.loads
    """Unserializer function to unserialize data after reading it from the cache."""

    _forced_adapter: Optional[StoragePort] = field(
        init=False, default=None
    )  # for unit-testing only
    __service: Optional[Service] = field(
        init=False, default=None
    )  # cache of the Service object

    @property
    def _service(self) -> Service:
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
            log_cache_hit=self.log_cache_hit,
            log_cache_miss=self.log_cache_miss,
            cache_hit_hook=self.cache_hit_hook,
            cache_miss_hook=self.cache_miss_hook,
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
        hook_userdata: Optional[Any] = None,
    ) -> Any:
        """Read the value for the given key (with given invalidation tags).

        If the key does not exist (or invalidated), None is returned.

        `hook_userdata` is an optional variable that can be transmitted to custom cache hooks (useless else).

        Raised:
            CacheMiss: if the key does not exist (or expired/invalidated).

        """
        tmp = self._service.get_value(key, tags or [], hook_userdata=hook_userdata)
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
    ):
        """Decorator for caching the result of a function.

        Notes:

        - for method, you should use `method_decorator` instead (because with `method_decorator` the first argument `self` is ignored in automatic key generation)
        - the result of the function must be pickleable

        - `tags` and `lifetime` are the same as for `set` method (but `tags` can also be a callable here to provide dynamic tags)
        - `key` is an optional function that can be used to generate a custom key
        - `hook_userdata` is an optional variable that can be transmitted to custom cache hooks (useless else)

        If you don't provide a `key` argument, a key is automatically generated from the function name/location and its calling arguments (they must be JSON serializable).
        You can override this behavior by providing a custom `key` function with following signature:

        ```python
        def custom_key(*args, **kwargs) -> str:
            # {your code here to generate key}
            # note: info about the decorated function will be added in kwargs under the key "rtc_call_info"
            #       (type: CacheCallInfo object)
            # make your own key from *args, **kwargs that are the calling arguments of the decorated function
            return key
        ```

        If you are interested by settings dynamic tags (i.e. tags that are computed at runtime depending on the function calling arguments), you can provide a callable for `tags` argument
        with the following signature:

        ```python
        def dynamic_tags(*args, **kwargs) -> List[str]:
            # {your code here to generate tags}
            # note: info about the decorated function will be added in kwargs under the key "rtc_call_info"
            #       (type: CacheCallInfo object)
            # make your own tags from *args, **kwargs that are the calling arguments of the decorated function
            return tags
        ```

        """
        if callable(tags):
            return self._service.decorator(
                [],
                lifetime=lifetime,
                dynamic_tag_names=tags,
                dynamic_key=key,
                hook_userdata=hook_userdata,
                serializer=self._serialize,
                unserializer=self._unserialize,
            )
        else:
            return self._service.decorator(
                tags or [],
                lifetime=lifetime,
                dynamic_key=key,
                hook_userdata=hook_userdata,
                serializer=self._serialize,
                unserializer=self._unserialize,
            )

    def method_decorator(
        self,
        tags: Optional[Union[List[str], Callable[..., List[str]]]] = None,
        lifetime: Optional[int] = None,
        key: Optional[Callable[..., str]] = None,
        hook_userdata: Optional[Any] = None,
    ):
        """Decorator for caching the result of a method.

        Notes:

        - for functions, you should use `function_decorator` instead (because with `method_decorator` the first argument is ignored in automatic key generation)
        - the result of the method must be pickleable

        - `tags` and `lifetime` are the same as for `set` method (but `tags` can also be a callable here to provide dynamic tags)
        - `key` is an optional method that can be used to generate a custom key
        - `hook_userdata` is an optional variable that can be transmitted to custom cache hooks (useless else)

        If you don't provide a `key` argument, a key is automatically generated from the method name/location and its calling arguments (they must be JSON serializable).
        You can override this behavior by providing a custom `key` function with following signature:

        ```python
        def custom_key(*args, **kwargs) -> str:
            # {your code here to generate key}
            # note: info about the decorated method will be added in kwargs under the key "rtc_call_info"
            #       (type: CacheCallInfo object)
            # make your own key from *args, **kwargs that are the calling arguments of the decorated method
            return key
        ```

        If you are interested by settings dynamic tags (i.e. tags that are computed at runtime depending on the method calling arguments), you can provide a callable for `tags` argument
        with the following signature:

        ```python
        def dynamic_tags(*args, **kwargs) -> List[str]:
            # {your code here to generate tags}
            # note: info about the decorated method will be added in kwargs under the key "rtc_call_info"
            #       (type: CacheCallInfo object)
            # make your own tags from *args, **kwargs that are the calling arguments of the decorated method
            return tags
        ```

        """
        if callable(tags):
            return self._service.decorator(
                [],
                lifetime=lifetime,
                dynamic_tag_names=tags,
                dynamic_key=key,
                ignore_first_argument=True,
                hook_userdata=hook_userdata,
                serializer=self._serialize,
                unserializer=self._unserialize,
            )
        else:
            return self._service.decorator(
                tags or [],
                lifetime=lifetime,
                dynamic_key=key,
                ignore_first_argument=True,
                hook_userdata=hook_userdata,
                serializer=self._serialize,
                unserializer=self._unserialize,
            )
