# redis-tagged-cache

## What is it?

`redis-tagged-cache` is a Python 3.7+ cache library backed with Redis **with O(1) tags-based invalidation system**.

### Low level example

Installation: `pip install redis-tagged-cache`

Usage:

```python
from rtc import RedisTaggedCache

cache = RedisTaggedCache(
    namespace="foo",
    host="localhost",
    port=6379,
)

invalidation_tags = ["tag1", "tag2"]  # tags are only strings of your choice

# Let's store something in the cache under the key "key1" (with a 60s lifetime)
cache.set("key1", b"value1", tags=invalidation_tags, lifetime=60)

print(cache.get("key1", tags=invalidation_tags))  # will output b"value1" (cache hit!)

# Let's invalidate a tag (O(1) operation)
cache.invalidate("tag2")

# As the "key1" entry is tagged with "tag1" and "tag2"...
# ...the entry is invalidated (because we just invalidated "tag2")

print(cache.get("key1", tags=invalidation_tags))  # will output None (cache miss!)
```

### High level example

```python
from redis_tagged_cache import RedisTaggedCache

cache = RedisTaggedCache(
    namespace="foo",
    host="localhost",
    port=6379,
)

class A:

    @cache.method_decorator(lifetime=60, tags=["tag1", "tag2"])
    def slow_method(self, arg1: str, arg2: str = "foo"):
        print("called")
        return arg1 + arg2

if __name__ == "__main__":
    a = A()
    print(a.slow_method("foo", arg2="bar"))  # will output "called" and "foobar" (cache miss)
    print(a.slow_method("foo", arg2="bar"))  # will output "foobar" (cache hit)
    print(a.slow_method("foo2", arg2="bar"))  # will output "called" and "foo2bar" (cache miss)

# Note: for plain functions, you can use @cache.function_decorator that works the same way
```

## Pros & Cons

### Pros

All methods have a O(1) complexity regarding the number of keys. The invalidation is synchronous and very fast event if you invalidate millions of keys.

Note: complexity is O(n) regarding the number of tags.

### Cons

The invalidation system does not really remove keys from redis. Invalidated entries are inaccessible (from the API) but they are not removed when the invalidation occurred. They are going to expire by themselves.

**Be sure to configure your redis instance as a cache with capped memory (see `maxmemory` configuration parameter) and `maxmemory-policy allkeys-lru` settings about keys [automatic eviction](https://redis.io/docs/latest/develop/reference/eviction/)**

## Dev

As we support Python 3.7+ for the runtime, the dev environment requires Python 3.9+.

- `make lint`: for linting the code
- `make test`: for executing test

(the poetry env will be automatically created)


