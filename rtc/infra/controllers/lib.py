from dataclasses import dataclass, field
from typing import Callable, List, Optional, Union

from rtc.app.service import Service
from rtc.app.storage import StoragePort
from rtc.infra.adapters.storage.blackhole import BlackHoleStorageAdapter
from rtc.infra.adapters.storage.redis import RedisStorageAdapter


@dataclass
class RedisTaggedCache:
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
    """If True, the cache is disabled (no read, no write)."""

    log_cache_hit: bool = True
    """If True, log cache hits with standard logging with a debug message."""

    log_cache_miss: bool = True
    """If True, log cache miss with standard logging with a debug message."""

    cache_hit_hook: Optional[Callable[[str, List[str]], None]] = None
    """Optional custom hook called when a cache hit occurs.

    Note: the hook is called with the key and the list of tags.

    """

    cache_miss_hook: Optional[Callable[[str, List[str]], None]] = None
    """Optional custom hook called when a cache miss occurs.

    Note: the hook is called with the key and the list of tags.

    """

    _forced_adapter: Optional[StoragePort] = field(init=False, default=None)
    __service: Optional[Service] = field(init=False, default=None)

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

    def get(self, key: str, tags: List[str]) -> Optional[bytes]:
        """Read the value for the given key (with given invalidation tags).

        If the key does not exist (or invalidated), None is returned.

        """
        return self._service.get_value(key, tags)

    def set(
        self,
        key: str,
        value: Union[str, bytes],
        tags: List[str],
        lifetime: Optional[int] = None,
    ) -> None:
        """Set a value for the given key (with given invalidation tags).

        Lifetime (in seconds) can be set (default to None: default expiration,
        0 means no expiration).

        """
        if isinstance(value, bytes):
            self._service.set_value(key, value, tags, lifetime)
        else:
            self._service.set_value(key, value.encode("utf-8"), tags, lifetime)

    def delete(self, key: str, tags: List[str]) -> None:
        """Delete the entry for the given key (with given invalidation tags).

        If the key does not exist (or invalidated), no exception is raised.

        """
        self._service.delete_value(key, tags)

    def invalidate(self, tags: Union[str, List[str]]) -> None:
        """Invalidate entries with given tag/tags."""
        if isinstance(tags, str):
            self._service.invalidate_tags([tags])
        else:
            self._service.invalidate_tags(tags)

    def invalidate_all(self) -> None:
        """Invalidate all entries."""
        self._service.invalidate_all()

    def function_decorator(
        self,
        tags: List[str],
        lifetime: Optional[int] = None,
        dynamic_tag_names: Optional[Callable[..., List[str]]] = None,
    ):
        return self._service.function_decorator(
            tags, lifetime=lifetime, dynamic_tag_names=dynamic_tag_names
        )

    def method_decorator(
        self,
        tags: List[str],
        lifetime: Optional[int] = None,
        dynamic_tag_names: Optional[Callable[..., List[str]]] = None,
    ):
        return self._service.method_decorator(
            tags, lifetime=lifetime, dynamic_tag_names=dynamic_tag_names
        )
