import pytest

from rtc.app.storage import StoragePort, StorageService
from rtc.infra.adapters.storage.dict import DictStorageAdapter


@pytest.fixture
def adapter() -> StoragePort:
    return DictStorageAdapter()


@pytest.fixture
def service(adapter: StoragePort):
    return StorageService(namespace="foo", adapter=adapter)


def test_basic(service: StorageService):
    service.set("key1", "hash1", b"value1", 10)
    assert service.get("key1", "hash1") == b"value1"
    service.delete("key1", "hash1")
    assert service.get("key1", "hash1") is None
    service.set("key1", "hash1", b"value1")
    assert service.get("key1", "hash1") == b"value1"
    service.delete("key1", "hash1")
