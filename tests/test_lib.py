import datetime
import os
import time
import uuid
from threading import Thread
from typing import List

import pytest

from rtc.app.service import CacheInfo
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


def test_function_decorator_with_hook(instance: RedisTaggedCache):
    calls = []

    def cache_hook(
        cache_key: str,
        cache_tags: List[str],
        cache_info: CacheInfo,
        userdata=None,
        **kwargs,
    ):
        if cache_info.hit:
            assert userdata == "foo"
            assert cache_info is not None
            assert cache_info.filepath == __file__
            assert cache_info.class_name == ""
            assert cache_info.function_name == "decorated"
            calls.append("hit")

    instance.cache_hook = cache_hook

    @instance.function_decorator(tags=["tag1", "tag2"], hook_userdata="foo")
    def decorated(*args, **kwargs):
        return [args, kwargs]

    decorated(1, "2", foo="bar")
    decorated(1, "2", foo="bar")
    assert len(calls) == 1
    assert calls[0] == "hit"


def test_method_decorator_with_hook(instance: RedisTaggedCache):
    calls = []

    def cache_hook(
        cache_key: str,
        cache_tags: List[str],
        cache_info: CacheInfo,
        userdata=None,
        **kwargs,
    ):
        if cache_info.hit:
            assert userdata == "foo"
            assert cache_info is not None
            assert cache_info.filepath == __file__
            assert cache_info.class_name == "A"
            assert cache_info.function_name == "decorated"
            calls.append("hit")

    instance.cache_hook = cache_hook

    class A:
        @instance.method_decorator(tags=["tag1", "tag2"], hook_userdata="foo")
        def decorated(self, *args, **kwargs):
            return [args, kwargs]

    a = A()
    a.decorated(1, "2", foo="bar")
    a.decorated(1, "2", foo="bar")
    assert len(calls) == 1
    assert calls[0] == "hit"


def test_method_decorator_with_lock(instance: RedisTaggedCache):
    calls = []

    class A:
        @instance.method_decorator(tags=["tag1", "tag2"], lock=True, lock_timeout=5)
        def decorated(self, *args, **kwargs):
            calls.append("called")
            time.sleep(3)
            return [args, kwargs]

    def wait_and_call(a: A):
        time.sleep(1)
        res = a.decorated(1, "2", foo="bar")
        assert res == [(1, "2"), {"foo": "bar"}]

    a = A()
    t = Thread(target=wait_and_call, args=(a,))
    t.start()

    before = datetime.datetime.now()
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]

    assert len(calls) == 1
    t.join()
    assert len(calls) == 1
    after = datetime.datetime.now()
    assert (after - before).total_seconds() < 4


def test_method_decorator_with_high_concurrency_lock(instance: RedisTaggedCache):
    calls = []

    class A:
        @instance.method_decorator(tags=["tag1", "tag2"], lock=True, lock_timeout=5)
        def decorated(self, *args, **kwargs):
            calls.append("called")
            time.sleep(2)
            return [args, kwargs]

    def call(a: A):
        res = a.decorated(1, "2", foo="bar")
        assert res == [(1, "2"), {"foo": "bar"}]

    a = A()

    # Let's call the function with different arguments to avoid a kind of race conditions in tag values
    res = a.decorated(0, "", foo="bar")
    assert res == [(0, ""), {"foo": "bar"}]
    calls.pop()  # let's remove the call from the list

    threads = []
    for _ in range(0, 100):
        t = Thread(target=call, args=(a,))
        threads.append(t)
    before = datetime.datetime.now()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1
    after = datetime.datetime.now()
    assert (after - before).total_seconds() < 4
