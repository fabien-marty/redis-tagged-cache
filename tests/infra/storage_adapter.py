import time

from rtc.app.storage import StoragePort


def _test_basic(adapter: StoragePort):
    adapter.set("ns", "key", "123", b"value", 10)
    assert adapter.get("ns", "key", "123") == b"value"
    assert adapter.get("ns", "key", "456") is None
    adapter.delete("ns", "key", "123")
    assert adapter.get("ns", "key", "123") is None


def _test_expiration(adapter: StoragePort):
    adapter.set("ns", "key", "123", b"value", 1)
    assert adapter.get("ns", "key", "123") == b"value"
    time.sleep(2)
    assert adapter.get("ns", "key", "123") is None


def _test_no_expiration(adapter: StoragePort):
    adapter.set("ns", "key", "123", b"value", 0)
    assert adapter.get("ns", "key", "123") == b"value"
    time.sleep(2)
    assert adapter.get("ns", "key", "123") == b"value"


def _test_multiple_values(adapter: StoragePort):
    adapter.set("ns", "key1", "123", b"value1", 10)
    adapter.set("ns", "key2", "123", b"value2", 10)
    assert adapter.get("ns", "key1", "123") == b"value1"
    assert adapter.get("ns", "key2", "123") == b"value2"
    adapter.delete("ns", "key1", "123")
    assert adapter.get("ns", "key1", "123") is None
    assert adapter.get("ns", "key2", "123") == b"value2"


def _test_delete_nonexistent(adapter: StoragePort):
    assert adapter.delete("ns", "key1", "789") is False
