import time
from typing import Any, Optional

import pytest

from rtc.app.exc import CacheMiss
from rtc.app.metadata import MetadataPort, MetadataService
from rtc.app.serializer import DEFAULT_SERIALIZER, DEFAULT_UNSERIALIZER
from rtc.app.service import GetOrLockResult, Service
from rtc.app.storage import StoragePort, StorageService
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


def test_basic_bytes(service: Service):
    assert service.set_bytes("key1", b"value1", ["tag1", "tag2"]) is True
    val = service.get_bytes("key1", ["tag2", "tag1"])
    assert val == b"value1"
    val = service.get_bytes("key2")
    assert val is None
    val = service.get_bytes("key1", ["tag1"])
    assert val is None
    val = service.get_bytes("key1", ["tag2"])
    assert val is None
    val = service.get_bytes("key1", ["tag1", "tag2", "tag3"])
    assert val is None
    assert service.invalidate_tags(["tag3", "tag2"]) is True
    val = service.get_bytes("key1", ["tag2", "tag1"])
    assert val is None
    assert service.set_bytes("key1", b"value1", ["tag1", "tag2"]) is True
    assert service.invalidate_all() is True
    val = service.get_bytes("key1", ["tag2", "tag1"])
    assert val is None


def test_basic(service: Service):
    assert service.set("key1", ["value1", "value2"], ["tag1", "tag2"]) is True
    val = service.get("key1", ["tag2", "tag1"])
    assert val == ["value1", "value2"]
    with pytest.raises(CacheMiss):
        service.get("key2")
    assert service.set("key2", None) is True
    assert service.get("key2") is None


def test_expiration(service: Service):
    assert service.set("key1", ["value1", "value2"], ["tag1", "tag2"], 1) is True
    assert service.get("key1", ["tag2", "tag1"]) == ["value1", "value2"]
    time.sleep(2)
    with pytest.raises(CacheMiss):
        service.get("key1", ["tag2", "tag1"])


def test_get_or_lock_result():
    with pytest.raises(ValueError):
        GetOrLockResult(full_miss=True, full_hit=True)
    with pytest.raises(ValueError):
        GetOrLockResult(value=b"value", lock_id="foo")


def bad_serializer(value: Any) -> Optional[bytes]:
    if value == 1:
        return None
    elif value == 2:
        raise ValueError("Bad serializer")
    else:
        return DEFAULT_SERIALIZER(value)


def bad_unserializer(value: bytes) -> Any:
    if value == b"1":
        return None
    elif value == b"2":
        raise ValueError("Bad unserializer")
    else:
        return DEFAULT_UNSERIALIZER(value)


def test_bad_serializer(service: Service):
    service.serializer = bad_serializer
    assert service.set("key", 1) is False
    assert service.set("key", 2) is False
    assert service.set("key", 3) is True
    assert service.get("key") == 3


def test_bad_unserializer(service: Service):
    service.unserializer = bad_unserializer
    service.set_bytes("key", b"1")
    assert service.get("key") is None
    service.set_bytes("key", b"2")
    with pytest.raises(CacheMiss):
        service.get("key")
