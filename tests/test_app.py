from typing import List

import pytest

from rtc.app.service import Service
from rtc.infra.adapters.storage.dict import DictStorageAdapter


@pytest.fixture
def service() -> Service:
    return Service(storage_adapter=DictStorageAdapter())


def test_basic(service: Service):
    service.set_value("key", b"value", ["tag1", "tag2"])
    assert service.get_value("key", ["tag1", "tag2"]) == b"value"
    assert service.get_value("key", ["tag1"]) is None
    assert service.get_value("key", ["tag2"]) is None
    assert service.get_value("key", ["tag1", "tag2", "tag3"]) is None
    service.delete_value("key", ["tag1", "tag2"])
    assert service.get_value("key", ["tag1", "tag2"]) is None


def test_tags_order(service: Service):
    service.set_value("key", b"value", ["tag1", "tag2"])
    assert service.get_value("key", ["tag1", "tag2"]) == b"value"
    assert service.get_value("key", ["tag2", "tag1"]) == b"value"


def test_invalidate_tags(service: Service):
    service.set_value("key", b"value", ["tag1", "tag2"])
    assert service.get_value("key", ["tag1", "tag2"]) == b"value"
    assert service.get_value("key", ["tag1"]) is None
    assert service.get_value("key", ["tag2"]) is None
    service.invalidate_tags(["tag3", "tag2"])
    assert service.get_value("key", ["tag1", "tag2"]) is None

    service.set_value("key", b"value", ["tag1", "tag2"])
    assert service.get_value("key", ["tag1", "tag2"]) == b"value"
    service.invalidate_tags(["tag3", "tag4"])
    assert service.get_value("key", ["tag1", "tag2"]) == b"value"
    service.invalidate_tags(["tag1"])
    assert service.get_value("key", ["tag1", "tag2"]) is None


def test_namespace(service: Service):
    other_service = Service(storage_adapter=DictStorageAdapter(), namespace="foo")
    service.set_value("key", b"value", ["tag1", "tag2"])
    assert service.get_value("key", ["tag1", "tag2"]) == b"value"
    assert other_service.get_value("key", ["tag1", "tag2"]) is None


def test_invalidate_all(service: Service):
    service.set_value("key", b"value1", ["tag1", "tag2"])
    service.set_value("key", b"value2", ["tag3"])
    service.set_value("key", b"value3", [])
    assert service.get_value("key", ["tag1", "tag2"]) == b"value1"
    assert service.get_value("key", ["tag3"]) == b"value2"
    assert service.get_value("key", []) == b"value3"
    service.invalidate_all()
    assert service.get_value("key", ["tag1", "tag2"]) is None
    assert service.get_value("key", ["tag3"]) is None
    assert service.get_value("key", []) is None


def test_function_decorator(service: Service):
    @service.function_decorator(tag_names=["tag1", "tag2"])
    def decorated(*args, **kwargs):
        service.set_value("called", b"called", tag_names=[])
        return [args, kwargs]

    res = decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert service.get_value("called", tag_names=[]) == b"called"
    service.delete_value("called", tag_names=[])
    assert service.get_value("called", tag_names=[]) is None

    res = decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert service.get_value("called", tag_names=[]) is None

    res = decorated(1, 2, foo="bar")
    assert res == [(1, 2), {"foo": "bar"}]
    assert service.get_value("called", tag_names=[]) == b"called"
    service.delete_value("called", tag_names=[])
    assert service.get_value("called", tag_names=[]) is None


def test_function_decorator_multiple(service: Service):
    @service.function_decorator(tag_names=["tag1", "tag2"])
    def decorated(*args, **kwargs):
        service.set_value("called", b"called", tag_names=[])
        return [1, args, kwargs]

    @service.function_decorator(tag_names=["tag1", "tag2"])
    def decorated2(*args, **kwargs):
        service.set_value("called2", b"called2", tag_names=[])
        return [2, args, kwargs]

    res = decorated(1, "2", foo="bar")
    assert res == [1, (1, "2"), {"foo": "bar"}]
    assert service.get_value("called", tag_names=[]) == b"called"
    assert service.get_value("called2", tag_names=[]) is None

    res = decorated2(1, "2", foo="bar")
    assert res == [2, (1, "2"), {"foo": "bar"}]
    assert service.get_value("called2", tag_names=[]) == b"called2"


def test_method_decorator(service: Service):
    class A:
        @service.method_decorator(tag_names=["tag1", "tag2"])
        def decorated(self, *args, **kwargs):
            service.set_value("called", b"called", tag_names=[])
            return [args, kwargs]

    a = A()
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert service.get_value("called", tag_names=[]) == b"called"
    service.delete_value("called", tag_names=[])
    assert service.get_value("called", tag_names=[]) is None

    service.invalidate_tags(["tag2"])
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert service.get_value("called", tag_names=[]) == b"called"
    service.delete_value("called", tag_names=[])
    assert service.get_value("called", tag_names=[]) is None


def dynamic_tags(self, *args, **kwargs) -> List[str]:
    assert args == (1, "2")
    return ["tag3"]


def test_dynamic_tags(service: Service):
    class A:
        @service.method_decorator(
            tag_names=["tag1", "tag2"], dynamic_tag_names=dynamic_tags
        )
        def decorated(self, *args, **kwargs):
            service.set_value("called", b"called", tag_names=[])
            return [args, kwargs]

    a = A()
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert service.get_value("called", tag_names=[]) == b"called"
    service.delete_value("called", tag_names=[])

    service.invalidate_tags(["tag3"])
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert service.get_value("called", tag_names=[]) == b"called"
