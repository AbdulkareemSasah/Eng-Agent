"""The network guard of the whole test tree (spec 0009 AC36): non-loopback connections and model requests refused."""

import socket

import pytest


def test_non_loopback_connect_is_refused() -> None:
    for family, address in (
        (socket.AF_INET, ("192.0.2.1", 9)),
        (socket.AF_INET, ("example.test", 80)),
        (socket.AF_INET6, ("2001:db8::1", 9, 0, 0)),
    ):
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
        except OSError:  # the family is not available on this machine (for example IPv6 disabled)
            continue
        with sock:
            sock.settimeout(0.2)
            with pytest.raises(OSError, match="non-loopback"):
                sock.connect(address)
            with pytest.raises(OSError, match="non-loopback"):
                sock.connect_ex(address)
    with pytest.raises(OSError, match="non-loopback"):
        socket.create_connection(("192.0.2.1", 9), timeout=0.2)

    # loopback stays allowed (the local page tests of spec 0006 need it)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.create_connection(server.getsockname(), timeout=2) as client:
            assert client.getpeername() == server.getsockname()


def test_model_requests_are_refused() -> None:
    from pydantic_ai import models

    assert models.ALLOW_MODEL_REQUESTS is False
