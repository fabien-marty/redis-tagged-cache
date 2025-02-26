import pytest

from rtc.app.hash import HASH_SIZE_IN_BYTES
from rtc.app.metadata import MetadataPort, MetadataService
from rtc.infra.adapters.metadata.dict import DictMetadataAdapter


@pytest.fixture
def adapter() -> MetadataPort:
    return DictMetadataAdapter()


@pytest.fixture
def service(adapter: MetadataPort):
    return MetadataService(namespace="foo", adapter=adapter)


def test_basic(service: MetadataService):
    hash1 = service.get_metadata_hash(["tag1", "tag2"])
    assert len(hash1) >= HASH_SIZE_IN_BYTES
    hash2 = service.get_metadata_hash(["tag2", "tag1"])
    assert hash1 == hash2
    hash3 = service.get_metadata_hash(["tag2", "tag3", "tag1"])
    assert hash3 != hash2
    service.invalidate_tags(["tag3"])
    hash4 = service.get_metadata_hash(["tag2", "tag3", "tag1"])
    assert hash4 != hash3
    service.invalidate_all()
    hash5 = service.get_metadata_hash(["tag1", "tag2"])
    assert hash5 != hash1


def test_lock(service: MetadataService):
    lock1 = service.lock("key1", "hash1")
    assert lock1 is not None
    service.unlock("key1", "hash1", lock1)
