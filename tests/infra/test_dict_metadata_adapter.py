import pytest

from rtc.app.metadata import MetadataPort
from rtc.infra.adapters.metadata.dict import DictMetadataAdapter
from tests.infra.metadata_adapter import (
    _test_get_or_set_tag_values,
    _test_invalidate_tags,
    _test_lock,
    _test_lock_timeout,
    _test_lock_wait,
)


@pytest.fixture
def adapter() -> MetadataPort:
    return DictMetadataAdapter()


def test_get_or_set_tag_values(adapter: MetadataPort):
    _test_get_or_set_tag_values(adapter)


def test_invalidate_tags(adapter: MetadataPort):
    _test_invalidate_tags(adapter)


def test_lock(adapter: MetadataPort):
    _test_lock(adapter)


def test_lock_timeout(adapter: MetadataPort):
    _test_lock_timeout(adapter)


def test_lock_wait(adapter: MetadataPort):
    _test_lock_wait(adapter)
