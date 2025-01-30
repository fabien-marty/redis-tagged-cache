import datetime
import os
import time
from threading import Thread

import pytest

from rtc.app.storage import StoragePort
from rtc.infra.adapters.storage.dict import DictStorageAdapter
from rtc.infra.adapters.storage.redis import RedisStorageAdapter

REDIS_HOST = os.getenv("REDIS_HOST", "")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


@pytest.fixture
def adapter() -> StoragePort:
    if REDIS_HOST:
        return RedisStorageAdapter(
            redis_kwargs={"host": REDIS_HOST, "port": REDIS_PORT}
        )
    return DictStorageAdapter()


def test_basic(adapter):
    adapter.set("key", b"value")
    assert adapter.get("key") == b"value"
    adapter.delete("key")
    assert adapter.get("key") is None
    adapter.delete("foo")


def test_mget(adapter):
    adapter.set("key1", b"value1")
    adapter.set("key2", b"value2")
    assert adapter.mget(["key1", "key2"]) == [b"value1", b"value2"]
    adapter.mdelete(["key1", "key2"])
    assert adapter.mget(["key1", "key2"]) == [None, None]


def test_lock(adapter):
    # lock an item that does not exist
    lock_id = adapter.lock("key1", timeout=3600)
    assert lock_id is not None
    adapter.unlock("key1", lock_id)
    # lock an item that exists
    adapter.set("key1", b"value1")
    lock_id = adapter.lock("key1", timeout=3600)
    assert lock_id is not None
    adapter.unlock("key1", lock_id)


def test_lock_timeout(adapter):
    lock_id = adapter.lock("key1", timeout=2)
    assert lock_id is not None
    lock_id2 = adapter.lock("key1", timeout=1)
    assert lock_id2 is None
    time.sleep(1)
    lock_id3 = adapter.lock("key1", timeout=1)
    assert lock_id3 is not None
    adapter.unlock("key1", lock_id3)


def test_lock_concurrency(adapter):
    def _thread_run(x: StoragePort):
        lock_id = x.lock("key1", timeout=10, waiting=10)
        assert lock_id is not None
        x.unlock("key1", lock_id)

    before = datetime.datetime.now()
    lock_id = adapter.lock("key1", timeout=3)
    assert lock_id is not None
    threads = [Thread(target=_thread_run, args=(adapter,)) for _ in range(0, 100)]
    for thread in threads:
        thread.start()
    time.sleep(2)
    adapter.unlock("key1", lock_id)
    for thread in threads:
        thread.join()
    after = datetime.datetime.now()
    assert (after - before).total_seconds() < 4
