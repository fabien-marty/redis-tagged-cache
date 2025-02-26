import os

import pytest

from rtc.app.metadata import MetadataPort
from rtc.infra.adapters.metadata.redis import RedisMetadataAdapter
from tests.infra.metadata_adapter import (
    _test_get_or_set_tag_values,
    _test_invalidate_tags,
    _test_lock,
    _test_lock_timeout,
    _test_lock_wait,
)

REDIS_HOST = os.getenv("REDIS_HOST", "")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


@pytest.fixture
def adapter() -> MetadataPort:
    return RedisMetadataAdapter(redis_kwargs={"host": REDIS_HOST, "port": REDIS_PORT})


@pytest.mark.skipif(REDIS_HOST == "", reason="REDIS_HOST is not set")
def test_get_or_set_tag_values(adapter: MetadataPort):
    _test_get_or_set_tag_values(adapter)


@pytest.mark.skipif(REDIS_HOST == "", reason="REDIS_HOST is not set")
def test_invalidate_tags(adapter: MetadataPort):
    _test_invalidate_tags(adapter)


@pytest.mark.skipif(REDIS_HOST == "", reason="REDIS_HOST is not set")
def test_lock(adapter: MetadataPort):
    _test_lock(adapter)


@pytest.mark.skipif(REDIS_HOST == "", reason="REDIS_HOST is not set")
def test_lock_timeout(adapter: MetadataPort):
    _test_lock_timeout(adapter)


@pytest.mark.skipif(REDIS_HOST == "", reason="REDIS_HOST is not set")
def test_lock_wait(adapter: MetadataPort):
    _test_lock_wait(adapter)
