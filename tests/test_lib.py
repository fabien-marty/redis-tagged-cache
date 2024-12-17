import os
import uuid
from typing import List

import pytest

from rtc.infra.adapters.storage.dict import DictStorageAdapter
from rtc.infra.controllers.lib import CacheMiss, RedisTaggedCache

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
    with pytest.raises(CacheMiss):
        instance.get("foo", tags=["tag1", "tag2"])
    instance.set("foo", b"value", tags=["tag1", "tag2"])
    assert instance.get("foo", tags=["tag1", "tag2"]) == b"value"
    instance.invalidate("tag2")
    with pytest.raises(CacheMiss):
        instance.get("foo", tags=["tag1", "tag2"])


def test_mget(instance: RedisTaggedCache):
    instance.set("foo1", b"value1", tags=["tag1", "tag2"])
    instance.set("foo2", b"value2", tags=["tag1", "tag2"])
    values = instance.mget(["foo1", "foo2", "foo3"], tags=["tag1", "tag2"])
    assert values[0] == b"value1"
    assert values[1] == b"value2"
    assert isinstance(values[2], CacheMiss)
    instance.invalidate_all()
    values = instance.mget(["foo1", "foo2", "foo3"], tags=["tag1", "tag2"])
    assert isinstance(values[0], CacheMiss)
    assert isinstance(values[1], CacheMiss)
    assert isinstance(values[2], CacheMiss)


def test_blackhole():
    inst = _instance(disabled=True)
    inst.set("foo", b"value", tags=["tag1", "tag2"])
    with pytest.raises(CacheMiss):
        inst.get("foo", tags=["tag1", "tag2"])
    inst.delete("foo", tags=["tag1", "tag2"])
    with pytest.raises(CacheMiss):
        inst.get("foo", tags=["tag1", "tag2"])
    inst.invalidate("tag2")
    with pytest.raises(CacheMiss):
        inst.get("foo", tags=["tag1", "tag2"])


def test_function_decorator(instance: RedisTaggedCache):
    @instance.function_decorator(tags=["tag1", "tag2"])
    def decorated(*args, **kwargs):
        instance.set("called", b"called", tags=[])
        return [args, kwargs]

    res = decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert instance.get("called", tags=[]) == b"called"
    instance.delete("called", tags=[])
    with pytest.raises(CacheMiss):
        instance.get("called", tags=[])

    res = decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    with pytest.raises(CacheMiss):
        instance.get("called", tags=[])

    res = decorated(1, 2, foo="bar")
    assert res == [(1, 2), {"foo": "bar"}]
    assert instance.get("called", tags=[]) == b"called"
    instance.delete("called", tags=[])
    with pytest.raises(CacheMiss):
        instance.get("called", tags=[])


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
    with pytest.raises(CacheMiss):
        instance.get("called", tags=[])

    instance.invalidate("tag2")
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert instance.get("called", tags=[]) == b"called"
    instance.delete("called", tags=[])
    with pytest.raises(CacheMiss):
        instance.get("called", tags=[])


def test_invalidate_all(instance: RedisTaggedCache):
    instance.set("key", b"value1", ["tag1", "tag2"])
    instance.set("key", b"value2", ["tag3"])
    instance.set("key", b"value3", [])
    assert instance.get("key", ["tag1", "tag2"]) == b"value1"
    assert instance.get("key", ["tag3"]) == b"value2"
    assert instance.get("key", []) == b"value3"
    instance.invalidate_all()
    with pytest.raises(CacheMiss):
        instance.get("key", ["tag1", "tag2"])
    with pytest.raises(CacheMiss):
        instance.get("key", ["tag3"])
    with pytest.raises(CacheMiss):
        instance.get("key", [])


def test_hooks(instance: RedisTaggedCache):
    calls = []

    def cache_hit_hook(key, tags, userdata):
        assert key == "key1"
        assert tags == ["tag1", "tag2"]
        assert userdata is None
        calls.append("hit")

    def cache_miss_hook(key, tags, userdata):
        assert key == "key2"
        assert tags == ["tag3"]
        assert userdata is None
        calls.append("miss")

    instance.cache_hit_hook = cache_hit_hook
    instance.cache_miss_hook = cache_miss_hook
    instance.set("key1", b"value1", ["tag1", "tag2"])
    assert instance.get("key1", ["tag1", "tag2"]) == b"value1"
    assert calls == ["hit"]
    with pytest.raises(CacheMiss):
        instance.get("key2", ["tag3"])
    assert calls == ["hit", "miss"]


def test_hooks_userdata(instance: RedisTaggedCache):
    calls = []

    def cache_hit_hook(key, tags, userdata):
        assert key == "key1"
        assert tags == ["tag1", "tag2"]
        assert userdata == "foo"
        calls.append("hit")

    def cache_miss_hook(key, tags, userdata):
        assert key == "key2"
        assert tags == ["tag3"]
        assert userdata == "foo"
        calls.append("miss")

    instance.cache_hit_hook = cache_hit_hook
    instance.cache_miss_hook = cache_miss_hook
    instance.set("key1", b"value1", ["tag1", "tag2"])
    assert instance.get("key1", ["tag1", "tag2"], hook_userdata="foo") == b"value1"
    assert calls == ["hit"]
    with pytest.raises(CacheMiss):
        instance.get("key2", ["tag3"], hook_userdata="foo")
    assert calls == ["hit", "miss"]


def dynamic_tags(self, *args, **kwargs) -> List[str]:
    assert args == (1, "2")
    return ["tag1", "tag2", "tag3"]


def dynamic_key(self, *args, **kwargs) -> str:
    assert args == (1, "2")
    return "fookey"


def test_dynamic_tags(instance: RedisTaggedCache):
    class A:
        @instance.method_decorator(tags=dynamic_tags)
        def decorated(self, *args, **kwargs):
            instance.set("called", b"called", tags=[])
            return [args, kwargs]

    a = A()
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert instance.get("called", tags=[]) == b"called"
    instance.delete("called", tags=[])

    instance.invalidate(["tag3"])
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert instance.get("called", tags=[]) == b"called"


def test_dynamic_key(instance: RedisTaggedCache):
    class A:
        @instance.method_decorator(tags=dynamic_tags, key=dynamic_key)
        def decorated(self, *args, **kwargs):
            instance.set("called", b"called", tags=[])
            return [args, kwargs]

    a = A()
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert instance.get("called", tags=[]) == b"called"
    instance.delete("called", tags=[])

    assert instance.get("fookey", tags=["tag1", "tag2", "tag3"]) is not None
