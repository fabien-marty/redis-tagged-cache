from rtc import CacheMiss, RedisTaggedCache

cache = RedisTaggedCache(
    namespace="foo",
    host="localhost",
    port=6379,
)

invalidation_tags = ["tag1", "tag2"]  # tags are only strings of your choice

# Let's store something in the cache under the key "key1"
# (with a 60s lifetime)
cache.set("key1", "my value", tags=invalidation_tags, lifetime=60)

# it will output "my value" (cache hit!)
print(cache.get("key1", tags=invalidation_tags))

# Let's invalidate a tag (O(1) operation)
cache.invalidate("tag2")

# As the "key1" entry is tagged with "tag1" and "tag2"...
# ...the entry is invalidated (because we just invalidated "tag2")

# It will print "cache miss"
try:
    cache.get("key1", tags=invalidation_tags)
except CacheMiss:
    print("cache miss")
