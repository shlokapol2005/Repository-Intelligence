class Foo:
    def bar(self):
        def inner_helper():
            pass
        return inner_helper

    async def baz(self):
        pass


def top_level():
    pass


def outer():
    def nested():
        pass
    return nested
