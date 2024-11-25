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
