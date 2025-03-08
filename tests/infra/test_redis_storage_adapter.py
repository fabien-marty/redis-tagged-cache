import os

import pytest

from rtc.app.storage import StoragePort
from rtc.infra.adapters.storage.redis import RedisStorageAdapter
from tests.infra.storage_adapter import (
    _test_basic,
    _test_delete_nonexistent,
    _test_expiration,
    _test_multiple_values,
    _test_no_expiration,
)

REDIS_HOST = os.getenv("REDIS_HOST", "")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


@pytest.fixture
def adapter() -> StoragePort:
    return RedisStorageAdapter(redis_kwargs={"host": REDIS_HOST, "port": REDIS_PORT})


@pytest.mark.skipif(REDIS_HOST == "", reason="REDIS_HOST is not set")
def test_basic(adapter: StoragePort):
    _test_basic(adapter)


@pytest.mark.skipif(REDIS_HOST == "", reason="REDIS_HOST is not set")
def test_expiration(adapter: StoragePort):
    _test_expiration(adapter)


@pytest.mark.skipif(REDIS_HOST == "", reason="REDIS_HOST is not set")
def test_no_expiration(adapter: StoragePort):
    _test_no_expiration(adapter)


@pytest.mark.skipif(REDIS_HOST == "", reason="REDIS_HOST is not set")
def test_multiple_values(adapter: StoragePort):
    _test_multiple_values(adapter)


@pytest.mark.skipif(REDIS_HOST == "", reason="REDIS_HOST is not set")
def test_delete_nonexistent(adapter: StoragePort):
    _test_delete_nonexistent(adapter)
