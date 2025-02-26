import inspect
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import wrapt

from rtc.app.hash import short_hash
from rtc.app.serializer import DEFAULT_SERIALIZER, DEFAULT_UNSERIALIZER
from rtc.app.service import Service
from rtc.app.types import CacheInfo

LOGGER = logging.getLogger("rtc.app.decorator")


def _get_key(
    cache_info: CacheInfo,
    key: Optional[Callable[..., str]],
    instance: Any,
    *decorated_args,
    **decorated_kwargs,
) -> Optional[str]:
    if key is not None:
        try:
            if instance is None:
                return key(*decorated_args, **decorated_kwargs)
            else:
                return key(instance, *decorated_args, **decorated_kwargs)
        except Exception:
            LOGGER.warning(
                "error while computing dynamic key => cache bypassed",
                exc_info=True,
            )
        return None
    try:
        serialized_args = json.dumps(
            [
                cache_info._dump(),
                decorated_args,
                decorated_kwargs,
            ],
            sort_keys=True,
        ).encode("utf-8")
        return short_hash(serialized_args)
    except Exception:
        LOGGER.warning(
            "arguments are not JSON serializable => cache bypassed",
            exc_info=True,
        )
        return None


def _get_full_tag_names(
    tags: Optional[Union[List[str], Callable[..., List[str]]]],
    instance: Any,
    *decorated_args,
    **decorated_kwargs,
) -> Optional[List[str]]:
    if callable(tags):
        try:
            if instance is None:
                return tags(*decorated_args, **decorated_kwargs)
            else:
                return tags(instance, *decorated_args, **decorated_kwargs)
        except Exception:
            LOGGER.warning(
                "error while computing dynamic tag names => cache bypassed",
                exc_info=True,
            )
            return None
    return tags or []


def cache_decorator(
    *,
    service: Service,
    tags: Optional[Union[List[str], Callable[..., List[str]]]] = None,
    lifetime: Optional[int] = None,
    key: Optional[Callable[..., str]] = None,
    hook_userdata: Optional[Any] = None,
    serializer: Callable[[Any], Optional[bytes]] = DEFAULT_SERIALIZER,
    unserializer: Callable[[bytes], Any] = DEFAULT_UNSERIALIZER,
    lock: bool = False,
    lock_timeout: int = 5,
):
    @wrapt.decorator
    def wrapper(wrapped: Callable, instance: Any, args: Tuple, kwargs: Dict) -> Any:
        before = time.perf_counter()
        class_name: str = ""
        if instance is not None:
            try:
                class_name = instance.__class__.__name__
            except Exception:
                pass
        cache_info = CacheInfo(
            filepath=inspect.getfile(wrapped),
            class_name=class_name,
            function_name=wrapped.__name__,
            function_args=args,
            function_kwargs=kwargs,
            method_decorator=instance is not None,
        )
        ckey = _get_key(
            cache_info,
            key,
            instance,
            *args,
            **kwargs,
        )
        full_tag_names = _get_full_tag_names(tags, instance, *args, **kwargs)
        lock_id: Optional[str] = None
        if ckey is not None and full_tag_names is not None:
            serialized_res: Optional[bytes]
            if lock:
                get_or_lock_result = service._get_bytes_or_lock_id(
                    ckey,
                    full_tag_names,
                    lock_timeout=lock_timeout,
                )
                serialized_res = get_or_lock_result.value
                lock_id = get_or_lock_result.lock_id
                metadata_hash = get_or_lock_result.metadata_hash
                cache_info.lock_full_hit = get_or_lock_result.full_hit
                cache_info.lock_full_miss = get_or_lock_result.full_miss
                cache_info.lock_waiting_ms = get_or_lock_result.waiting_ms
            else:
                serialized_res, metadata_hash = service._get_bytes(
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
                    service._safe_call_hook(
                        ckey, full_tag_names, cache_info, hook_userdata
                    )
                    return unserialized
                except Exception:
                    logging.warning(
                        "error while unserializing cache value => cache bypassed",
                        exc_info=True,
                    )
                finally:
                    if lock_id and metadata_hash:
                        service._unlock(ckey, metadata_hash, lock_id)
        # cache miss => let's call the decorated function
        before_decorated = time.perf_counter()
        res = wrapped(*args, **kwargs)
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
            if serialized is not None and metadata_hash is not None:
                cache_info.serialized_size = len(serialized)
                service.set_bytes(ckey, serialized, full_tag_names, lifetime=lifetime)
        if ckey and lock_id and metadata_hash:
            service.metadata_service.unlock(ckey, metadata_hash, lock_id)
        if ckey:
            cache_info.elapsed = time.perf_counter() - before
            service._safe_call_hook(
                ckey,
                full_tag_names if full_tag_names else [],
                cache_info,
                hook_userdata,
            )
        return res

    return wrapper
