from rtc import RedisTaggedCache

cache = RedisTaggedCache(
    namespace="foo",
    host="localhost",
    port=6379,
)


class A:
    @cache.decorator(lifetime=60, tags=["tag1", "tag2"])
    def slow_method(self, arg1: str, arg2: str = "foo"):
        print("called")
        return arg1 + arg2


if __name__ == "__main__":
    a = A()

    # It will output "called" and "foobar" (cache miss)
    print(a.slow_method("foo", arg2="bar"))

    # It will output "foobar" (cache hit)
    print(a.slow_method("foo", arg2="bar"))

    # It will output "called" and "foo2bar" (cache miss)
    print(a.slow_method("foo2", arg2="bar"))
