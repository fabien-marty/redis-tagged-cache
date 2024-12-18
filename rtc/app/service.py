import base64
import hashlib
import inspect
import json
import logging
import pickle
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Union

from rtc.app.storage import StoragePort

PROTOCOL_AVAILABLE = False
try:
    from typing import Protocol

    PROTOCOL_AVAILABLE = True
except Exception:
    pass


SPECIAL_ALL_TAG_NAME = "@@@all@@@"


def _sha256_binary_hash(data: Union[str, bytes]) -> bytes:
    """Generate a binary hash (bytes) of the given string or bytes."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    h = hashlib.sha256(data)
    return h.digest()


def _sha256_text_hash(data: Union[str, bytes]) -> str:
    """Generate a hexa hash (str) of the given string or bytes."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    h = hashlib.sha256(data)
    return h.hexdigest()


def short_hash(data: Union[str, bytes]) -> str:
    """Generate a short alpha-numeric hash of the given string or bytes."""
    h = _sha256_binary_hash(data)[0:8]
    return (
        base64.b64encode(h)
        .decode("utf-8")
        .replace("=", "")
        .replace("+", "-")
        .replace("/", "_")
    )


def get_logger() -> logging.Logger:
    return logging.getLogger("redis-tagged-cache")


class CacheMiss(Exception):
    """Exception raised when a cache miss occurs."""

    pass


@dataclass(frozen=True)
class CacheCallInfo:
    """Class containing location infos about the cache call.

    This is only used in cache hit/miss hooks and only for decorators.

    """

    filepath: str
    """File path of the decorated function."""

    class_name: str
    """Class name (empty for functions) of the decorated function."""

    function_name: str
    """Function name of the decorated function/method."""

    def _dump(self) -> List:
        return [self.filepath, self.class_name, self.function_name]


if PROTOCOL_AVAILABLE:

    class CacheHook(Protocol):
        def __call__(
            self,
            cache_key: str,
            cache_tags: List[str],
            userdata: Any = None,
            call_info: Optional[CacheCallInfo] = None,
            **kwargs,
        ) -> None: ...

else:
    CacheHook = Callable  # type: ignore


@dataclass
class Service:
    storage_adapter: StoragePort
    namespace: str = "default"
    default_lifetime: Optional[int] = None
    lifetime_for_tags: Optional[int] = None
    log_cache_hit: bool = True
    log_cache_miss: bool = True
    cache_hit_hook: Optional[CacheHook] = None
    cache_miss_hook: Optional[CacheHook] = None

    namespace_hash: str = field(init=False, default="")
    logger: logging.Logger = field(default_factory=get_logger)

    def __post_init__(self):
        self.namespace_hash = short_hash(self.namespace)

    def safe_call_hook(
        self,
        hook: Optional[CacheHook],
        str,
        tag_names: List[str],
        userdata: Optional[Any] = None,
        call_info: Optional[CacheCallInfo] = None,
    ) -> None:
        """Call the given hook with the given arguments.

        If an exception is raised, it is caught and logged. If the hook is None, nothing is done.

        """
        if not hook:
            return
        try:
            hook(str, tag_names, userdata=userdata, call_info=call_info)
        except Exception:
            self.logger.warning(f"Error while calling hook {hook}", exc_info=True)

    def resolve_lifetime(self, lifetime: Optional[int]) -> Optional[int]:
        """Resolve the given lifetime with the default value.

        If the given value is not None => return it. Else return the default value
        set at the instance level.

        """
        if lifetime is not None:
            return lifetime
        return self.default_lifetime

    def get_storage_tag_key(self, tag_name: str) -> str:
        """Compute and return the storage_key for the given tag name."""
        tag_name_hash = short_hash(tag_name)
        return f"rtc:{self.namespace_hash}:t:{tag_name_hash}"

    def get_tag_values(self, tag_names: List[str]) -> List[bytes]:
        """Returns tag values (as a list) for a list of tag names.

        If a tag does not exist (aka does not have a value), a value is generated
        and returned.

        """
        res: List[bytes] = []
        tag_storage_keys = [
            self.get_storage_tag_key(tag_name) for tag_name in tag_names
        ]
        values = self.storage_adapter.mget(tag_storage_keys)
        for tag_storage_key, value in zip(tag_storage_keys, values):
            if value is None:
                # First use of this tag! Let's generate a fist value
                # Yes, there is a race condition here, but it's not a big problem
                # (maybe we are going to invalidate the tag twice)
                new_value = short_hash(uuid.uuid4().bytes).encode("utf-8")
                self.storage_adapter.set(
                    tag_storage_key,
                    new_value,
                    lifetime=self.lifetime_for_tags or self.default_lifetime,
                )
                res.append(new_value)
            else:
                res.append(value)
        return res

    def get_storage_value_key(self, value_key: str, tag_names: List[str]) -> str:
        """Compute and return the storage_key for the given value_key (and tag names)."""
        special_tag_names = tag_names[:]
        if SPECIAL_ALL_TAG_NAME not in tag_names:
            special_tag_names.append(SPECIAL_ALL_TAG_NAME)
        tags_values = self.get_tag_values(sorted(special_tag_names))
        tags_hash = short_hash(b"".join(tags_values))
        value_key_hash = short_hash(value_key)
        return f"rtc:{self.namespace_hash}:v:{value_key_hash}:{tags_hash}"

    def invalidate_tags(self, tag_names: List[str]) -> None:
        """Invalidate a list of tag names."""
        for tag_name in tag_names:
            if tag_name == SPECIAL_ALL_TAG_NAME:
                self.logger.debug("Invalidating all cache")
            else:
                self.logger.debug(f"Invalidating tag {tag_name}")
        self.storage_adapter.mdelete([self.get_storage_tag_key(t) for t in tag_names])

    def invalidate_all(self) -> None:
        """Invalidate all entries."""
        self.invalidate_tags([SPECIAL_ALL_TAG_NAME])

    def set_value(
        self,
        key: str,
        value: bytes,
        tag_names: List[str],
        lifetime: Optional[int] = None,
    ) -> None:
        """Set a value for the given key (with given invalidation tags).

        Lifetime can be set (default to 0: no expiration)

        """
        storage_key = self.get_storage_value_key(key, tag_names)
        resolved_lifetime = self.resolve_lifetime(lifetime)
        self.logger.debug(
            "set value for cache key: %s and tags: %s", key, ", ".join(tag_names)
        )
        self.storage_adapter.set(storage_key, value, lifetime=resolved_lifetime)

    def get_value(
        self,
        key: str,
        tag_names: List[str],
        hook_userdata: Optional[Any] = None,
        call_info: Optional[CacheCallInfo] = None,
    ) -> Optional[bytes]:
        """Read the value for the given key (with given invalidation tags).

        If the key does not exist (or invalidated), None is returned.

        """
        storage_key = self.get_storage_value_key(key, tag_names)
        res = self.storage_adapter.mget([storage_key])[0]
        if res is None:
            if self.log_cache_miss:
                self.logger.debug(
                    "cache miss for key: %s and tags: %s", key, ", ".join(tag_names)
                )
            self.safe_call_hook(
                self.cache_miss_hook, key, tag_names, hook_userdata, call_info
            )
        else:
            if self.log_cache_hit:
                self.logger.debug(
                    "cache hit for key: %s and tags: %s", key, ", ".join(tag_names)
                )
            self.safe_call_hook(
                self.cache_hit_hook, key, tag_names, hook_userdata, call_info
            )
        return res

    def delete_value(self, key: str, tag_names: List[str]) -> None:
        """Delete the entry for the given key (with given invalidation tags).

        If the key does not exist (or invalidated), no exception is raised.

        """
        storage_key = self.get_storage_value_key(key, tag_names)
        self.logger.debug(
            "delete cache for key: %s and tags: %s", key, ", ".join(tag_names)
        )
        self.storage_adapter.delete(storage_key)

    def decorator(
        self,
        tag_names: List[str],
        ignore_first_argument: bool = False,
        lifetime: Optional[int] = None,
        dynamic_tag_names: Optional[Callable[..., List[str]]] = None,
        dynamic_key: Optional[Callable[..., str]] = None,
        hook_userdata: Optional[Any] = None,
        serializer: Callable[[Any], Optional[bytes]] = pickle.dumps,
        unserializer: Callable[[bytes], Any] = pickle.loads,
    ):
        def inner_decorator(f: Any):
            def wrapped(*args: Any, **kwargs: Any):
                key: str = ""
                args_index: int = 0
                class_name: str = ""
                if ignore_first_argument and len(args) > 0:
                    args_index = 1
                    try:
                        class_name = args[0].__class__.__name__
                    except Exception:
                        pass
                call_info = CacheCallInfo(
                    filepath=inspect.getfile(f),
                    class_name=class_name,
                    function_name=f.__name__,
                )
                if dynamic_key is not None:
                    try:
                        if "rtc_call_info" in kwargs:
                            key = dynamic_key(*args, **kwargs)
                        else:
                            key = dynamic_key(
                                *args, **{**kwargs, "rtc_call_info": call_info}
                            )
                    except Exception:
                        logging.warning(
                            "error while computing dynamic key => cache bypassed",
                            exc_info=True,
                        )
                else:
                    try:
                        serialized_args = json.dumps(
                            [
                                call_info._dump(),
                                args[args_index:],
                                kwargs,
                            ],
                            sort_keys=True,
                        ).encode("utf-8")
                        key = _sha256_text_hash(serialized_args)
                    except Exception:
                        logging.warning(
                            "arguments are not JSON serializable => cache bypassed",
                            exc_info=True,
                        )
                if key:
                    if dynamic_tag_names:
                        try:
                            if "rtc_call_info" in kwargs:
                                full_tag_names = tag_names + dynamic_tag_names(
                                    *args, **kwargs
                                )
                            else:
                                full_tag_names = tag_names + dynamic_tag_names(
                                    *args, **{**kwargs, "rtc_call_info": call_info}
                                )
                        except Exception:
                            logging.warning(
                                "error while computing dynamic tag names => cache bypassed",
                                exc_info=True,
                            )
                            key = ""
                    else:
                        full_tag_names = tag_names
                if key:
                    serialized_res = self.get_value(
                        key,
                        full_tag_names,
                        hook_userdata=hook_userdata,
                        call_info=call_info,
                    )
                    if serialized_res is not None:
                        # cache hit!
                        try:
                            return unserializer(serialized_res)
                        except Exception:
                            logging.warning(
                                "error while unserializing cache value => cache bypassed",
                                exc_info=True,
                            )
                res = f(*args, **kwargs)
                if key:
                    serialized = serializer(res)
                    if serialized is not None:
                        self.set_value(
                            key, serialized, full_tag_names, lifetime=lifetime
                        )
                return res

            return wrapped

        return inner_decorator
