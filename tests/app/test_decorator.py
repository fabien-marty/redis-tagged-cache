from typing import Iterable, List, Any

import pytest

from rtc.app.decorator import cache_decorator
from rtc.app.metadata import MetadataPort, MetadataService
from rtc.app.service import Service
from rtc.app.storage import StoragePort, StorageService
from rtc.app.types import CacheInfo
from rtc.infra.adapters.metadata.dict import DictMetadataAdapter
from rtc.infra.adapters.storage.dict import DictStorageAdapter

DEFAULT_NAMESPACE = "foo"


@pytest.fixture
def metadata_adapter() -> MetadataPort:
    return DictMetadataAdapter()


@pytest.fixture
def storage_adapter() -> StoragePort:
    return DictStorageAdapter()


@pytest.fixture
def metadata_service(metadata_adapter: MetadataPort):
    return MetadataService(namespace=DEFAULT_NAMESPACE, adapter=metadata_adapter)


@pytest.fixture
def storage_service(storage_adapter: StoragePort):
    return StorageService(namespace=DEFAULT_NAMESPACE, adapter=storage_adapter)


@pytest.fixture
def service(
    metadata_service: MetadataService, storage_service: StorageService
) -> Service:
    return Service(
        metadata_service=metadata_service,
        storage_service=storage_service,
        namespace=DEFAULT_NAMESPACE,
    )


def test_function_decorator(service: Service):
    @cache_decorator(service=service, tags=["tag1", "tag2"])
    def decorated(*args, **kwargs):
        service.set_bytes("called", b"called")
        return [args, kwargs]

    res = decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert service.get_bytes("called") == b"called"
    service.delete("called")
    assert service.get_bytes("called") is None

    res = decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert service.get_bytes("called") is None

    res = decorated(1, 2, foo="bar")
    assert res == [(1, 2), {"foo": "bar"}]
    assert service.get_bytes("called") == b"called"
    service.delete("called")
    assert service.get_bytes("called") is None


def test_function_decorator_multiple(service: Service):
    @cache_decorator(service=service, tags=["tag1", "tag2"])
    def decorated(*args, **kwargs):
        service.set_bytes("called", b"called")
        return [1, args, kwargs]

    @cache_decorator(service=service, tags=["tag1", "tag2"])
    def decorated2(*args, **kwargs):
        service.set_bytes("called2", b"called2")
        return [2, args, kwargs]

    res = decorated(1, "2", foo="bar")
    assert res == [1, (1, "2"), {"foo": "bar"}]
    assert service.get_bytes("called") == b"called"
    assert service.get_bytes("called2") is None

    res = decorated2(1, "2", foo="bar")
    assert res == [2, (1, "2"), {"foo": "bar"}]
    assert service.get_bytes("called2") == b"called2"


def test_method_decorator(service: Service):
    class A:
        @cache_decorator(service=service, tags=["tag1", "tag2"])
        def decorated(self, *args, **kwargs):
            service.set_bytes("called", b"called")
            return [args, kwargs]

    a = A()
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert service.get_bytes("called") == b"called"
    service.delete("called")
    assert service.get_bytes("called") is None

    service.invalidate_tags(["tag2"])
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert service.get_bytes("called") == b"called"
    service.delete("called")
    assert service.get_bytes("called") is None


def dynamic_tags(self, *args, **kwargs) -> List[str]:
    assert args == (1, "2")
    return ["tag1", "tag2", "tag3"]


def test_dynamic_tags(service: Service):
    class A:
        @cache_decorator(service=service, tags=dynamic_tags)
        def decorated(self, *args, **kwargs):
            service.set_bytes("called", b"called")
            return [args, kwargs]

    a = A()
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert service.get_bytes("called") == b"called"
    service.delete("called")

    service.invalidate_tags(["tag3"])
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert service.get_bytes("called") == b"called"


def dynamic_key(self, *args, **kwargs) -> str:
    return f"dynamic_key_{args[0]}_{args[1]}"


def test_dynamic_key(service: Service):
    class A:
        @cache_decorator(service=service, tags=["tag1"], key=dynamic_key)
        def decorated(self, *args, **kwargs):
            service.set_bytes("called", b"called")
            return [args, kwargs]

    a = A()
    # First call should miss cache and compute result
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert service.get_bytes("called") == b"called"
    service.delete("called")
    assert service.get_bytes("called") is None

    # Second call with same args should hit cache
    res = a.decorated(1, "2", foo="bar")
    assert res == [(1, "2"), {"foo": "bar"}]
    assert service.get_bytes("called") is None  # Should not be called again

    # Call with different args should miss cache and compute new result
    res = a.decorated(2, "3", foo="bar")
    assert res == [(2, "3"), {"foo": "bar"}]
    assert service.get_bytes("called") == b"called"  # Should be called for new key


def bad_cache_hook(
    cache_key: str,
    cache_tags: Iterable[str],
    cache_info: CacheInfo,
    userdata: Any = None,
):
    raise ValueError("Bad cache hook")


def test_bad_cache_hook(service: Service):
    service.cache_hook = bad_cache_hook

    @cache_decorator(service=service, tags=["tag1", "tag2"])
    def decorated(*args, **kwargs):
        service.set_bytes("called", b"called")
        return [1, args, kwargs]

    decorated("foo", 1, bar="baz")
    assert service.get_bytes("called") == b"called"
    assert service.delete("called") is True
    decorated("foo", 1, bar="baz")
    assert service.get_bytes("called") is None
