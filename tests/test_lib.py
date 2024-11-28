import os
import uuid

import pytest

from rtc.infra.adapters.storage.dict import DictStorageAdapter
from rtc.infra.controllers.lib import RedisTaggedCache

REDIS_HOST = os.getenv("REDIS_HOST", "")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


def _instance(**kwargs) -> RedisTaggedCache:
    if "namespace" not in kwargs:
        namespace = str(uuid.uuid4())
        kwargs = {"namespace": namespace, **kwargs}
    if REDIS_HOST:
        kwargs["host"] = REDIS_HOST
        kwargs["port"] = REDIS_PORT
    cache = RedisTaggedCache(**kwargs)
    if not REDIS_HOST and not kwargs.get("disabled", False):
        cache._forced_adapter = DictStorageAdapter()
    return cache


@pytest.fixture
def instance() -> RedisTaggedCache:
    return _instance()


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
    inst = _instance(disabled=True)
    inst.set("foo", b"value", tags=["tag1", "tag2"])
    assert inst.get("foo", tags=["tag1", "tag2"]) is None
    inst.delete("foo", tags=["tag1", "tag2"])
    assert inst.get("foo", tags=["tag1", "tag2"]) is None
    inst.invalidate("tag2")
    assert inst.get("foo", tags=["tag1", "tag2"]) is None


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


def test_hooks(instance: RedisTaggedCache):
    calls = []

    def cache_hit_hook(key, tags):
        assert key == "key1"
        assert tags == ["tag1", "tag2"]
        calls.append("hit")

    def cache_miss_hook(key, tags):
        assert key == "key2"
        assert tags == ["tag3"]
        calls.append("miss")

    instance.cache_hit_hook = cache_hit_hook
    instance.cache_miss_hook = cache_miss_hook
    instance.set("key1", b"value1", ["tag1", "tag2"])
    assert instance.get("key1", ["tag1", "tag2"]) == b"value1"
    assert calls == ["hit"]
    assert instance.get("key2", ["tag3"]) is None
    assert calls == ["hit", "miss"]
