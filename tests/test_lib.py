import os
import uuid
from typing import Optional

import pytest
import redis

from rtc.infra.adapters.storage.dict import DictStorageAdapter
from rtc.infra.controllers.lib import RedisTaggedCache

DONT_TEST_WITH_REDIS: bool = os.environ.get("RTC_DONT_TEST_WITH_REDIS", "0") == "1"
__REDIS_AVAILABLE: Optional[bool] = None


def is_redis_available() -> bool:
    global __REDIS_AVAILABLE
    if DONT_TEST_WITH_REDIS:
        return False
    if __REDIS_AVAILABLE is not None:
        return __REDIS_AVAILABLE
    r = redis.Redis(socket_connect_timeout=2, socket_timeout=2)
    try:
        __REDIS_AVAILABLE = r.ping() is True
    except Exception:
        __REDIS_AVAILABLE = False
    return __REDIS_AVAILABLE


@pytest.fixture
def instance() -> RedisTaggedCache:
    namespace = str(uuid.uuid4())
    cache = RedisTaggedCache(namespace=namespace)
    if is_redis_available():
        cache._forced_adapter = DictStorageAdapter()
    return cache


def test_basic(instance: RedisTaggedCache):
    instance.set("foo", b"value", tags=["tag1", "tag2"])
    assert instance.get("foo", tags=["tag1", "tag2"]) == b"value"
    instance.delete("foo", tags=["tag1", "tag2"])
    assert instance.get("foo", tags=["tag1", "tag2"]) is None
    instance.set("foo", b"value", tags=["tag1", "tag2"])
    assert instance.get("foo", tags=["tag1", "tag2"]) == b"value"
    instance.invalidate("tag2")
    assert instance.get("foo", tags=["tag1", "tag2"]) is None


def test_blackhole():
    instance = RedisTaggedCache(disabled=True)
    instance.set("foo", b"value", tags=["tag1", "tag2"])
    assert instance.get("foo", tags=["tag1", "tag2"]) is None
    instance.delete("foo", tags=["tag1", "tag2"])
    assert instance.get("foo", tags=["tag1", "tag2"]) is None
    instance.invalidate("tag2")
    assert instance.get("foo", tags=["tag1", "tag2"]) is None


def test_function_decorator(instance: RedisTaggedCache):
    @instance.function_decorator(tags=["tag1", "tag2"])
    def decorated(*args, **kwargs):
        instance.set("called", b"called", tags=[])
        return [args, kwargs]

    res = decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert instance.get("called", tags=[]) == b"called"
    instance.delete("called", tags=[])
    assert instance.get("called", tags=[]) is None

    res = decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert instance.get("called", tags=[]) is None

    res = decorated(1, 2, foo="bar")
    assert res == [(1, 2), {"foo": "bar"}]
    assert instance.get("called", tags=[]) == b"called"
    instance.delete("called", tags=[])
    assert instance.get("called", tags=[]) is None


def test_method_decorator(instance: RedisTaggedCache):
    class A:
        @instance.method_decorator(tags=["tag1", "tag2"])
        def decorated(self, *args, **kwargs):
            instance.set("called", b"called", tags=[])
            return [args, kwargs]

    a = A()
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert instance.get("called", tags=[]) == b"called"
    instance.delete("called", tags=[])
    assert instance.get("called", tags=[]) is None

    instance.invalidate("tag2")
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert instance.get("called", tags=[]) == b"called"
    instance.delete("called", tags=[])
    assert instance.get("called", tags=[]) is None


def test_invalidate_all(instance: RedisTaggedCache):
    instance.set("key", b"value1", ["tag1", "tag2"])
    instance.set("key", b"value2", ["tag3"])
    instance.set("key", b"value3", [])
    assert instance.get("key", ["tag1", "tag2"]) == b"value1"
    assert instance.get("key", ["tag3"]) == b"value2"
    assert instance.get("key", []) == b"value3"
    instance.invalidate_all()
    assert instance.get("key", ["tag1", "tag2"]) is None
    assert instance.get("key", ["tag3"]) is None
    assert instance.get("key", []) is None
