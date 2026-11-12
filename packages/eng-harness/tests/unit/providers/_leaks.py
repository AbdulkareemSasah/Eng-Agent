"""Leak walk for provider errors (spec 0009 AC10): the key and remote text must be unreachable from a raised error."""

import contextlib
from collections.abc import Mapping, Sequence

import httpx2


def assert_no_leak(err: BaseException, secrets: Sequence[str], bodies: Sequence[str] = ()) -> None:
    """Fail if a secret or a response-body text is reachable from ``err``.

    Walks the message, ``args``, attributes, ``__cause__``, ``__context__`` and every frame local of the traceback,
    recursing into containers, exceptions and httpx2 requests and responses. The failure message names the route, never
    the leaked text.
    """
    needles = [text for text in (*secrets, *bodies) if text]
    seen: set[int] = set()
    keep: list[object] = []  # keeps visited objects alive so that ids stay unique

    def check(text: str, route: str) -> None:
        assert not any(needle in text for needle in needles), f"leak reachable through {route}"

    def walk(obj: object, route: str) -> None:
        if id(obj) in seen:
            return
        seen.add(id(obj))
        keep.append(obj)
        if isinstance(obj, str):
            check(obj, route)
        elif isinstance(obj, bytes | bytearray):
            check(bytes(obj).decode("utf-8", "replace"), route)
        elif isinstance(obj, Mapping):
            for key, value in obj.items():
                walk(key, f"{route}.key")
                walk(value, f"{route}[]")
        elif isinstance(obj, list | tuple | set | frozenset):
            for item in obj:
                walk(item, f"{route}[]")
        elif isinstance(obj, BaseException):
            walk_exception(obj, route)
        elif isinstance(obj, httpx2.Request):
            walk(str(obj.url), f"{route}.url")
            walk(dict(obj.headers), f"{route}.headers")
            with contextlib.suppress(httpx2.RequestNotRead):
                walk(obj.content, f"{route}.content")
        elif isinstance(obj, httpx2.Response):
            walk(dict(obj.headers), f"{route}.headers")
            walk(obj.content, f"{route}.content")

    def walk_exception(exc: BaseException, route: str) -> None:
        walk(str(exc), f"{route}.str")
        walk(exc.args, f"{route}.args")
        walk(dict(vars(exc)), f"{route}.attributes")
        if exc.__cause__ is not None:
            walk(exc.__cause__, f"{route}.__cause__")
        if exc.__context__ is not None:
            walk(exc.__context__, f"{route}.__context__")
        tb = exc.__traceback__
        while tb is not None:
            for name, value in tb.tb_frame.f_locals.items():
                walk(value, f"{route}.frame {tb.tb_frame.f_code.co_name}.{name}")
            tb = tb.tb_next

    walk(err, "error")
