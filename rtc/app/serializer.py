# Default serialization functions
import pickle
from typing import Any, Callable, Optional

DEFAULT_SERIALIZER: Callable[[Any], Optional[bytes]] = pickle.dumps
DEFAULT_UNSERIALIZER: Callable[[bytes], Any] = pickle.loads
