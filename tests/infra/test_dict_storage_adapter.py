import pytest

from rtc.app.storage import StoragePort
from rtc.infra.adapters.storage.dict import DictStorageAdapter
from tests.infra.storage_adapter import (
    _test_basic,
    _test_expiration,
    _test_multiple_values,
    _test_no_expiration,
)


@pytest.fixture
def adapter() -> StoragePort:
    return DictStorageAdapter()


def test_basic(adapter: StoragePort):
    _test_basic(adapter)


def test_expiration(adapter: StoragePort):
    _test_expiration(adapter)


def test_no_expiration(adapter: StoragePort):
    _test_no_expiration(adapter)


def test_multiple_values(adapter: StoragePort):
    _test_multiple_values(adapter)
