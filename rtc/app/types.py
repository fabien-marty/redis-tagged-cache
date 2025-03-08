from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Tuple

PROTOCOL_AVAILABLE = False
try:
    from typing import Protocol

    PROTOCOL_AVAILABLE = True
except Exception:
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
    """If True, we decorated a method (and not a simple function)."""

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


if PROTOCOL_AVAILABLE:

    class CacheHook(Protocol):
        def __call__(
            self,
            cache_key: str,
            cache_tags: Iterable[str],
            cache_info: CacheInfo,
            userdata: Any = None,
        ) -> None:
            """Signature of cache hooks."""
            pass

else:
    CacheHook = Callable  # type: ignore
