import json
import logging
import pickle
from dataclasses import dataclass, field
from typing import Any, List, Optional, Union

from rtc.app.service import Service, short_hash
from rtc.app.storage import StoragePort
from rtc.infra.adapters.storage.blackhole import BlackHoleStorageAdapter
from rtc.infra.adapters.storage.redis import RedisStorageAdapter


@dataclass
class RedisTaggedCache:
    namespace: str = "default"
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    ssl: bool = False
    socket_timeout: int = 5
    socket_connect_timeout: int = 5
    default_lifetime: Optional[int] = None
    lifetime_for_tags: Optional[int] = None
    disabled: bool = False

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
            self._service.invalidate_tag(tags)
        else:
            self._service.invalidate_tags(tags)

    def invalidate_all(self) -> None:
        """Invalidate all entries."""
        self._service.invalidate_all()

    def _decorator(
        self,
        tags: List[str],
        ignore_first_argument: bool = False,
        lifetime: Optional[int] = None,
    ):
        def inner_decorator(f: Any):
            def wrapped(*args: Any, **kwargs: Any):
                key: str = ""
                args_index: int = 0
                if ignore_first_argument and len(args) > 0:
                    args_index = 1
                try:
                    serialized_args = json.dumps([args[args_index:], kwargs]).encode(
                        "utf-8"
                    )
                    key = short_hash(serialized_args)
                except Exception:
                    logging.warning(
                        "arguments are not JSON serializable => cache bypassed",
                        exc_info=True,
                    )
                if key:
                    serialized_res = self.get(key, tags)
                    if serialized_res is not None:
                        # cache hit!
                        return pickle.loads(serialized_res)
                res = f(*args, **kwargs)
                if key:
                    try:
                        serialized = pickle.dumps(res)
                    except Exception:
                        logging.warning(
                            "the returned value is not pickle serializable => cache bypassed",
                            exc_info=True,
                        )
                    else:
                        self.set(key, serialized, tags, lifetime=lifetime)
                return res

            return wrapped

        return inner_decorator

    def function_decorator(
        self,
        tags: List[str],
        lifetime: Optional[int] = None,
    ):
        return self._decorator(tags, lifetime=lifetime)

    def method_decorator(
        self,
        tags: List[str],
        lifetime: Optional[int] = None,
    ):
        return self._decorator(tags, ignore_first_argument=True, lifetime=lifetime)
