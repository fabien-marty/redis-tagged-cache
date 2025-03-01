import time

import pytest

from rtc.app.exc import CacheMiss
from rtc.app.metadata import MetadataPort, MetadataService
from rtc.app.service import Service
from rtc.app.storage import StoragePort, StorageService
from rtc.infra.adapters.metadata.bad import BadMetadataAdapter
from rtc.infra.adapters.storage.bad import BadStorageAdapter

DEFAULT_NAMESPACE = "foo"


@pytest.fixture
def metadata_adapter() -> BadMetadataAdapter:
    return BadMetadataAdapter()


@pytest.fixture
def storage_adapter() -> BadStorageAdapter:
    return BadStorageAdapter()


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


def test_basic(service: Service):
    assert service.set("key", "value") is False
    with pytest.raises(CacheMiss):
        service.get("key")
    assert service.delete("key") is False
    assert service.invalidate_tags(["tag"]) is False
    assert service.invalidate_all() is False
