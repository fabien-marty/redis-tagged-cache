import time

from rtc.app.metadata import MetadataPort


def _test_get_or_set_tag_values(adapter: MetadataPort):
    values = list(adapter.get_or_set_tag_values("ns", ["tag1", "tag2"], 10))
    assert len(values) == 2
    assert len(values[0]) >= 4
    assert len(values[1]) >= 4
    assert values[0] != values[1]
    new_values = list(adapter.get_or_set_tag_values("ns", ["tag2", "tag3"], 10))
    assert len(new_values) == 2
    assert len(new_values[0]) >= 4
    assert len(new_values[1]) >= 4
    assert new_values[0] == values[1]
    assert new_values[0] != new_values[1]


def _test_invalidate_tags(adapter: MetadataPort):
    values = list(adapter.get_or_set_tag_values("ns", ["tag1", "tag2"], 10))
    assert len(values) == 2
    assert len(values[0]) >= 4
    assert len(values[1]) >= 4
    assert values[0] != values[1]
    new_values = list(adapter.get_or_set_tag_values("ns", ["tag2", "tag1"], 10))
    assert len(new_values) == 2
    assert new_values[0] == values[1]
    assert new_values[1] == values[0]
    adapter.invalidate_tags("ns", ["tag1"])
    new_values2 = list(adapter.get_or_set_tag_values("ns", ["tag2", "tag1"], 10))
    assert len(new_values2) == 2
    assert new_values2[0] == new_values[0]
    assert new_values2[1] != new_values[1]


def _test_lock(adapter: MetadataPort):
    before = time.perf_counter()
    id = adapter.lock("ns", "key", "hash", 10, 1)
    after = time.perf_counter()
    assert id is not None
    assert after - before < 1
    adapter.unlock("ns", "key", "hash", id)


def _test_lock_timeout(adapter: MetadataPort):
    before = time.perf_counter()
    id1 = adapter.lock("ns", "key", "hash", 1, 10)
    after = time.perf_counter()
    assert id1 is not None
    assert after - before < 1
    before = time.perf_counter()
    id2 = adapter.lock("ns", "key", "hash", 10, 2)
    after = time.perf_counter()
    assert id2 is not None
    assert after - before > 1
    adapter.unlock("ns", "key", "hash", id1)  # to test if it doesn't raise
    adapter.unlock("ns", "key", "hash", id2)


def _test_lock_wait(adapter: MetadataPort):
    before = time.perf_counter()
    id1 = adapter.lock("ns", "key", "hash", 10, 2)
    after = time.perf_counter()
    assert id1 is not None
    assert after - before < 1
    before = time.perf_counter()
    id2 = adapter.lock("ns", "key", "hash", 10, 1)
    after = time.perf_counter()
    assert id2 is None
    assert after - before > 1
    adapter.unlock("ns", "key", "hash", id1)
