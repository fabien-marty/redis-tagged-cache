import pytest

from rtc.app.storage import StoragePort
from rtc.infra.adapters.storage.blackhole import BlackHoleStorageAdapter


@pytest.fixture
def adapter() -> StoragePort:
    return BlackHoleStorageAdapter()


def test_basic(adapter: StoragePort):
    adapter.set("ns", "key", "123", b"value", 10)
    assert adapter.get("ns", "key", "123") is None
    adapter.delete("ns", "key", "123")
    assert adapter.get("ns", "key", "123") is None
