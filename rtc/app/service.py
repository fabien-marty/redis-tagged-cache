import base64
import hashlib
import inspect
import json
import logging
import pickle
import time
import uuid
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from rtc.app.storage import StoragePort

PROTOCOL_AVAILABLE = False
try:
    from typing import Protocol

    PROTOCOL_AVAILABLE = True
except Exception:
    pass


SPECIAL_ALL_TAG_NAME = "@@@all@@@"
SHORT_HASH_BYTES = 8  # Number of bytes to use for short hash generation

# Default serialization functions
DEFAULT_SERIALIZER: Callable[[Any], Optional[bytes]] = pickle.dumps
DEFAULT_UNSERIALIZER: Callable[[bytes], Any] = pickle.loads


def _sha256_hash(data: Union[str, bytes]):
    """Generate a sha256 hash of the given string or bytes."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data)


def _sha256_binary_hash(data: Union[str, bytes]) -> bytes:
    """Generate a binary hash (bytes) of the given string or bytes."""
    return _sha256_hash(data).digest()


def _sha256_text_hash(data: Union[str, bytes]) -> str:
    """Generate a hexa hash (str) of the given string or bytes.

    Args:
        data: The data to hash.

    Returns:
        A hexadecimal hash of the given data.
    """
    return _sha256_hash(data).hexdigest()


def short_hash(data: Union[str, bytes]) -> str:
    """Generate a short alpha-numeric hash of the given string or bytes.

    This function takes a string or bytes input, generates a SHA-256 hash, takes the first 8 bytes,
    encodes it in URL-safe base64, and returns a clean alpha-numeric string by removing padding
    and replacing hyphens.

    Args:
        data: The input string or bytes to hash.

    Returns:
        A short alpha-numeric hash string derived from the input data.
    """
    h = _sha256_binary_hash(data)[0:SHORT_HASH_BYTES]
    return base64.urlsafe_b64encode(h).decode("utf-8").replace("=", "").replace("-", "")


def get_logger() -> logging.Logger:
    return logging.getLogger("redis-tagged-cache")


class CacheMiss(Exception):
    """Exception raised when a cache miss occurs."""

    pass


@dataclass
class CacheInfo:
    """Class containing location infos about the cache call.

    This is only used in cache hit/miss hooks.

    """

    filepath: str = ""
    """File path of the decorated function."""

    class_name: str = ""
    """Class name (empty for functions) of the decorated function."""

    function_name: str = ""
    """Function name of the decorated function/method."""

    function_args: Tuple[Any, ...] = field(default_factory=tuple)
    """Decorated function/method arguments (including self as first argument for methods) (*args)."""

    function_kwargs: Dict[str, Any] = field(default_factory=dict)
    """Decorated function/method keyword arguments (**kwargs)."""

    method_decorator: bool = False
    """If True, this comes from a method_decorator. Else from a function_decorator."""

    hit: bool = False
    """Cache hit (the value was found in the cache)."""

    elapsed: float = 0.0
    """Total elapsed time (in seconds). It includes the decorated function call in case of cache miss but excludes hooks."""

    decorated_elapsed: float = 0.0
    """Elapsed time of the decorated function call (in seconds), only in case of cache miss."""

    lock_waiting_ms: int = 0
    """Lock waiting time (in ms), only when used with cache decorators and lock=True."""

    lock_full_hit: bool = False
    """Lock full hit (no lock acquired at all, the value was cached before), only when used with cache decorators and lock=True."""

    lock_full_miss: bool = False
    """Lock full miss (we acquired a lock but the value was not cached after that => full cache miss), only when used with cache decorators and lock=True."""

    serialized_size: int = 0
    """Serialized size of the value (in bytes)."""

    # extra note: if lock_full_hit = False and lock_full_miss = False (when used with cache decorators and lock=True),
    # it means that the value was initially not here, so we acquired a lock but the value was cached after that (anti-dogpile effect)

    def _dump(self) -> List[str]:
        # Special method for cache decorators
        return [self.filepath, self.class_name, self.function_name]


@dataclass(frozen=True)
class GetOrLockResult:
    value: Optional[bytes] = None
    storage_key: Optional[str] = None
    lock_id: Optional[str] = None
    waiting_ms: int = 0
    full_hit: bool = False
    full_miss: bool = False


if PROTOCOL_AVAILABLE:

    class CacheHook(Protocol):
        def __call__(
            self,
            cache_key: str,
            cache_tags: List[str],
            cache_info: CacheInfo,
            userdata: Any = None,
        ) -> None:
            """Signature of cache hooks."""
            pass


else:
    CacheHook = Callable  # type: ignore


@dataclass
class Service:
    storage_adapter: StoragePort
    namespace: str = "default"
    default_lifetime: Optional[int] = None
    lifetime_for_tags: Optional[int] = None
    cache_hook: Optional[CacheHook] = None

    namespace_hash: str = field(init=False, default="")
    logger: logging.Logger = field(default_factory=get_logger)

    def __post_init__(self):
        self.namespace_hash = short_hash(self.namespace)

    def safe_call_hook(
        self,
        cache_key: str,
        tag_names: List[str],
        cache_info: CacheInfo,
        userdata: Optional[Any] = None,
    ) -> None:
        """Call the given hook with the given arguments.

        If an exception is raised, it is caught and logged. If the hook is None, nothing is done.

        """
        if not self.cache_hook:
            return
        try:
            self.cache_hook(
                cache_key, tag_names, userdata=userdata, cache_info=cache_info
            )
        except Exception:
            self.logger.warning(
                f"Error while calling hook {self.cache_hook}", exc_info=True
            )

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

    def _get_value(
        self,
        key: str,
        tag_names: List[str],
    ) -> Tuple[Optional[bytes], str]:
        """Read the value for the given key (with given invalidation tags).

        If the key does not exist (or invalidated), None is returned.

        Returns a tuple (value, storage_key).

        """
        storage_key = self.get_storage_value_key(key, tag_names)
        res = self.storage_adapter.get(storage_key)
        return res, storage_key

    def get_value_or_lock_id(
        self,
        key: str,
        tag_names: List[str],
        lock_timeout: int = 5,
    ) -> GetOrLockResult:
        """Read the value for the given key (with given invalidation tags).

        If this is a cache miss, a lock is acquired then we read the cache
        another time. If we get the value, the lock is released.

        If we still have a cache miss, None is returned as value but the lock_id
        is returned (as the second element of the tuple).

        """
        # first try without lock
        res, storage_key = self._get_value(key, tag_names)
        if res is not None:
            # cache hit
            return GetOrLockResult(value=res, storage_key=storage_key, full_hit=True)
        # cache miss => let's lock
        before = time.perf_counter()
        while True:
            lock_id = self.storage_adapter.lock(
                storage_key, timeout=lock_timeout, waiting=1
            )
            waiting_ms = int((time.perf_counter() - before) * 1000)
            try:
                # retry: maybe we have the value now?
                res, storage_key = self._get_value(key, tag_names)
                if res is not None:
                    # cache hit
                    return GetOrLockResult(
                        value=res,
                        storage_key=storage_key,
                        waiting_ms=waiting_ms,
                        lock_id=None,  # we return None here because we are going to release the lock in the finally clause
                    )
            finally:
                if res is not None and lock_id is not None:
                    self.storage_adapter.unlock(storage_key, lock_id)
            if lock_id or waiting_ms > 1000 * lock_timeout:
                break
        # cache miss (again)
        return GetOrLockResult(
            waiting_ms=waiting_ms,
            full_miss=True,
            lock_id=lock_id,
            storage_key=storage_key,
        )

    def get_value(
        self,
        key: str,
        tag_names: List[str],
    ) -> Optional[bytes]:
        """Read the value for the given key (with given invalidation tags).

        If the key does not exist (or invalidated), None is returned.

        """
        res, _ = self._get_value(key, tag_names)
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

    def _decorator_get_key(
        self,
        cache_info: CacheInfo,
        key: Optional[Callable[..., str]],
        decorated_args_index: int,
        *decorated_args,
        **decorated_kwargs,
    ) -> Optional[str]:
        if key is not None:
            try:
                return key(*decorated_args, **decorated_kwargs)
            except Exception:
                logging.warning(
                    "error while computing dynamic key => cache bypassed",
                    exc_info=True,
                )
            return None
        try:
            serialized_args = json.dumps(
                [
                    cache_info._dump(),
                    decorated_args[decorated_args_index:],
                    decorated_kwargs,
                ],
                sort_keys=True,
            ).encode("utf-8")
            return _sha256_text_hash(serialized_args)
        except Exception:
            logging.warning(
                "arguments are not JSON serializable => cache bypassed",
                exc_info=True,
            )
            return None

    def _decorator_get_full_tag_names(
        self,
        tags: Optional[Union[List[str], Callable[..., List[str]]]] = None,
        *decorated_args,
        **decorated_kwargs,
    ) -> Optional[List[str]]:
        if callable(tags):
            try:
                return tags(*decorated_args, **decorated_kwargs)
            except Exception:
                logging.warning(
                    "error while computing dynamic tag names => cache bypassed",
                    exc_info=True,
                )
                return None
        return tags

    def decorator(
        self,
        tags: Optional[Union[List[str], Callable[..., List[str]]]] = None,
        ignore_first_argument: bool = False,
        lifetime: Optional[int] = None,
        key: Optional[Callable[..., str]] = None,
        hook_userdata: Optional[Any] = None,
        serializer: Callable[[Any], Optional[bytes]] = DEFAULT_SERIALIZER,
        unserializer: Callable[[bytes], Any] = DEFAULT_UNSERIALIZER,
        lock: bool = False,
        lock_timeout: int = 5,
    ):
        def inner_decorator(f: Any):
            @wraps(f)
            def wrapped(*args: Any, **kwargs: Any):
                before = time.perf_counter()
                args_index: int = 0
                class_name: str = ""
                if ignore_first_argument and len(args) > 0:
                    args_index = 1
                    try:
                        class_name = args[0].__class__.__name__
                    except Exception:
                        pass
                cache_info = CacheInfo(
                    filepath=inspect.getfile(f),
                    class_name=class_name,
                    function_name=f.__name__,
                    function_args=args,
                    function_kwargs=kwargs,
                    method_decorator=ignore_first_argument,
                )
                ckey = self._decorator_get_key(
                    cache_info,
                    key,
                    args_index,
                    *args,
                    **kwargs,
                )
                full_tag_names = self._decorator_get_full_tag_names(
                    tags, *args, **kwargs
                )
                lock_id: Optional[str] = None
                storage_key: Optional[str] = None
                if ckey is not None and full_tag_names is not None:
                    serialized_res: Optional[bytes]
                    if lock:
                        get_or_lock_result = self.get_value_or_lock_id(
                            ckey,
                            full_tag_names,
                            lock_timeout=lock_timeout,
                        )
                        serialized_res = get_or_lock_result.value
                        lock_id = get_or_lock_result.lock_id
                        storage_key = get_or_lock_result.storage_key
                        cache_info.lock_full_hit = get_or_lock_result.full_hit
                        cache_info.lock_full_miss = get_or_lock_result.full_miss
                        cache_info.lock_waiting_ms = get_or_lock_result.waiting_ms
                    else:
                        serialized_res = self.get_value(
                            ckey,
                            full_tag_names,
                        )
                    if serialized_res is not None:
                        # cache hit!
                        cache_info.serialized_size = len(serialized_res)
                        try:
                            unserialized = unserializer(serialized_res)
                            cache_info.hit = True
                            cache_info.elapsed = time.perf_counter() - before
                            self.safe_call_hook(
                                ckey, full_tag_names, cache_info, hook_userdata
                            )
                            return unserialized
                        except Exception:
                            logging.warning(
                                "error while unserializing cache value => cache bypassed",
                                exc_info=True,
                            )
                        finally:
                            if lock_id and storage_key:
                                self.storage_adapter.unlock(storage_key, lock_id)
                # cache miss => let's call the decorated function
                before_decorated = time.perf_counter()
                res = f(*args, **kwargs)
                cache_info.decorated_elapsed = time.perf_counter() - before_decorated

                if ckey is not None and full_tag_names is not None:
                    serialized: Optional[bytes] = None
                    try:
                        serialized = serializer(res)
                    except Exception:
                        logging.warning(
                            "error while serializing cache value => cache bypassed",
                            exc_info=True,
                        )
                    if serialized is not None:
                        cache_info.serialized_size = len(serialized)
                        self.set_value(
                            ckey, serialized, full_tag_names, lifetime=lifetime
                        )
                if lock_id and storage_key:
                    self.storage_adapter.unlock(storage_key, lock_id)
                if ckey:
                    cache_info.elapsed = time.perf_counter() - before
                    self.safe_call_hook(
                        ckey,
                        full_tag_names if full_tag_names else [],
                        cache_info,
                        hook_userdata,
                    )
                return res

            return wrapped

        return inner_decorator
