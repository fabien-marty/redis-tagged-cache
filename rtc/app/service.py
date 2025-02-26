import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, List, Optional, Tuple

from rtc.app.exc import CacheException, CacheMiss
from rtc.app.metadata import MetadataService
from rtc.app.serializer import DEFAULT_SERIALIZER, DEFAULT_UNSERIALIZER
from rtc.app.storage import StorageService
from rtc.app.types import CacheHook, CacheInfo


@dataclass(frozen=True)
class GetOrLockResult:
    value: Optional[bytes] = None
    metadata_hash: Optional[str] = None
    lock_id: Optional[str] = None
    waiting_ms: int = 0
    full_hit: bool = False
    full_miss: bool = False

    def __post_init__(self):
        if self.full_hit and self.full_miss:
            raise ValueError("full_hit and full_miss cannot be True at the same time")
        if self.value is not None and self.lock_id is not None:
            raise ValueError("value and lock_id cannot be set at the same time")


def get_logger() -> logging.Logger:
    return logging.getLogger("rtc.app.service")


def _tag_names(tag_names: Optional[Iterable[str]]) -> Iterable[str]:
    if tag_names is None:
        return []
    return tag_names


@dataclass
class Service:
    metadata_service: MetadataService
    storage_service: StorageService
    namespace: str = "default"
    cache_hook: Optional[CacheHook] = None

    serializer: Callable[[Any], Optional[bytes]] = DEFAULT_SERIALIZER
    """Serializer function to serialize data before storing it in the cache."""

    unserializer: Callable[[bytes], Any] = DEFAULT_UNSERIALIZER
    """Unserializer function to unserialize data after reading it from the cache."""

    logger: logging.Logger = field(default_factory=get_logger)

    def _safe_call_hook(
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

    def invalidate_tags(self, tag_names: Iterable[str]) -> bool:
        """Invalidate a list of tag names."""
        try:
            self.metadata_service.invalidate_tags(tag_names)
            return True
        except CacheException:
            self.logger.warning(
                "cache exception during a tag invalidation => operation bypassed",
                exc_info=True,
            )
            return False

    def invalidate_all(self) -> bool:
        """Invalidate all entries."""
        try:
            self.metadata_service.invalidate_all()
            return True
        except CacheException:
            self.logger.warning(
                "cache exception during a tag invalidation => operation bypassed",
                exc_info=True,
            )
            return False

    def set_bytes(
        self,
        key: str,
        value: bytes,
        tag_names: Optional[Iterable[str]] = None,
        lifetime: Optional[int] = None,
    ) -> bool:
        """Set a value for the given key (with given invalidation tags).

        Lifetime can be set (<=0 means:no expiration, None means "use default value")

        """
        try:
            metadata_hash = self.metadata_service.get_metadata_hash(
                _tag_names(tag_names)
            )
            self.storage_service.set(
                key,
                metadata_hash,
                value,
                lifetime,
            )
            return True
        except CacheException:
            self.logger.warning(
                "cache exception when setting a key => cache bypassed", exc_info=True
            )
            return False

    def set(
        self,
        key: str,
        value: Any,
        tag_names: Optional[Iterable[str]] = None,
        lifetime: Optional[int] = None,
    ) -> bool:
        try:
            value_bytes = self.serializer(value)
        except Exception:
            self.logger.warning(
                "error when serializing provided data => cache bypassed",
                exc_info=True,
            )
            return False
        if value_bytes is None:
            self.logger.warning(
                "serializer returned None => cache bypassed",
                exc_info=True,
            )
            return False
        return self.set_bytes(key, value_bytes, tag_names, lifetime)

    def _get_bytes(
        self, key: str, tag_names: Optional[Iterable[str]] = None
    ) -> Tuple[Optional[bytes], Optional[str]]:
        try:
            metadata_hash = self.metadata_service.get_metadata_hash(
                _tag_names(tag_names)
            )
            return self.storage_service.get(key, metadata_hash), metadata_hash
        except CacheException:
            self.logger.warning(
                "cache exception when reading a key => cache bypassed", exc_info=True
            )
            return None, None

    def get_bytes(
        self, key: str, tag_names: Optional[Iterable[str]] = None
    ) -> Optional[bytes]:
        res, _ = self._get_bytes(key, tag_names)
        return res

    def get(self, key: str, tag_names: Optional[Iterable[str]] = None) -> Any:
        value_bytes = self.get_bytes(key, tag_names)
        if value_bytes is None:
            raise CacheMiss()
        try:
            return self.unserializer(value_bytes)
        except Exception:
            self.logger.warning(
                "error when unserializing cached data => cache bypassed",
                exc_info=True,
            )
            raise CacheMiss()

    def delete(self, key: str, tag_names: Optional[Iterable[str]] = None) -> bool:
        try:
            metadata_hash = self.metadata_service.get_metadata_hash(
                _tag_names(tag_names)
            )
            return self.storage_service.delete(key, metadata_hash)
        except CacheException:
            self.logger.warning("cache exception when deleting a key", exc_info=True)
            return False

    def __get_bytes_or_lock_id(
        self,
        key: str,
        tag_names: Iterable[str],
        lock_timeout: int = 5,
    ) -> GetOrLockResult:
        """Read the value for the given key (with given invalidation tags).

        If this is a cache miss, a lock is acquired then we read the cache
        another time. If we get the value, the lock is released.

        If we still have a cache miss, None is returned as value but the lock_id
        is returned (as the second element of the tuple).

        """
        # first try without lock
        res, metadata_hash = self._get_bytes(key, tag_names)
        if res is not None:
            # cache hit
            return GetOrLockResult(
                value=res, metadata_hash=metadata_hash, full_hit=True
            )
        # cache miss => let's lock
        before = time.perf_counter()
        while True:
            if metadata_hash is None:
                # cache exception => cache bypassed
                return GetOrLockResult(full_miss=True)
            lock_id = self.metadata_service.lock(
                key, metadata_hash, timeout=lock_timeout, waiting=1
            )
            # retry: maybe we have the value now?
            res, metadata_hash = self._get_bytes(key, tag_names)
            if res is not None and metadata_hash is not None:
                # cache hit
                # let's unlock
                self.metadata_service.unlock(key, metadata_hash, lock_id)
                return GetOrLockResult(
                    value=res,
                    metadata_hash=metadata_hash,
                    waiting_ms=int((time.perf_counter() - before) * 1000),
                    lock_id=None,
                )
            if lock_id or int(time.perf_counter() - before) > lock_timeout:
                break
        # cache miss (again)
        return GetOrLockResult(
            waiting_ms=int((time.perf_counter() - before) * 1000),
            full_miss=True,
            lock_id=lock_id,
            metadata_hash=metadata_hash,
        )

    def _get_bytes_or_lock_id(
        self,
        key: str,
        tag_names: Iterable[str],
        lock_timeout: int = 5,
    ) -> GetOrLockResult:
        try:
            return self.__get_bytes_or_lock_id(key, tag_names, lock_timeout)
        except CacheException:
            self.logger.warning(
                "cache exception when getting or locking a key", exc_info=True
            )
            return GetOrLockResult(full_miss=True)

    def _unlock(self, key: str, metadata_hash: str, lock_identifier: str) -> bool:
        try:
            self.metadata_service.unlock(key, metadata_hash, lock_identifier)
            return True
        except CacheException:
            self.logger.warning("cache exception when unlocking a key", exc_info=True)
            return False
