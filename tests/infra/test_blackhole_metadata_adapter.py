import time

import pytest

from rtc.app.metadata import MetadataPort
from rtc.infra.adapters.metadata.blackhole import BlackHoleMetadataAdapter


@pytest.fixture
def adapter() -> MetadataPort:
    return BlackHoleMetadataAdapter()


def test_get_or_set_tag_values(adapter: MetadataPort):
    values = list(adapter.get_or_set_tag_values("ns", ["tag1", "tag2"], 10))
    assert len(values) == 2
    assert len(values[0]) >= 4
    assert len(values[1]) >= 4
    assert values[0] != values[1]
    new_values = list(adapter.get_or_set_tag_values("ns", ["tag2", "tag3"], 10))
    assert len(new_values) == 2
    assert len(new_values[0]) >= 4
    assert len(new_values[1]) >= 4
    assert new_values[0] != values[1]
    assert new_values[0] != new_values[1]


def test_invalidate_tags(adapter: MetadataPort):
    values = list(adapter.get_or_set_tag_values("ns", ["tag1", "tag2"], 10))
    assert len(values) == 2
    assert len(values[0]) >= 4
    assert len(values[1]) >= 4
    assert values[0] != values[1]
    adapter.invalidate_tags("ns", ["tag1"], 10)
    new_values = list(adapter.get_or_set_tag_values("ns", ["tag2", "tag1"], 10))
    assert len(new_values) == 2
    assert new_values[0] != values[0]
    assert new_values[1] != values[1]


def test_lock(adapter: MetadataPort):
    before = time.perf_counter()
    id = adapter.lock("ns", "key", "hash", 10, 1)
    after = time.perf_counter()
    assert id is not None
    assert after - before < 1
    adapter.unlock("ns", "key", "hash", id)
