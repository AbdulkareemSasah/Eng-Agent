"""Lockdown after repeated refusals, and shutdown that frees the port (plan 0006 T6; AC28)."""

import logging
import socket
from urllib.parse import urlsplit

import pytest
from tests.helpers.page_client import RUN_DATA, PageClient, StubApp, serving

from eng_harness.pages import CSRF_FIELD, PageServer, PageSettings

FORM = {"decision": "approve", "reason": "ok"}


def _refuse(client: PageClient, kind: str) -> int:
    """Send one request refused for `kind` and return its status."""
    match kind:
        case "host":
            return client.get("/", headers={"Host": "evil.example"}).status
        case "origin":
            return client.post("/answer/req-1", FORM, headers={"Origin": "http://evil.example"}).status
        case "fetch-site":
            return client.post("/answer/req-1", FORM, headers={"Sec-Fetch-Site": "cross-site"}).status
        case "cookie":
            return client.get("/", headers={"Cookie": None}).status
        case "launch-code":
            return client.get("/launch?code=wrong").status
        case _:
            return client.post("/answer/req-1", FORM).status  # csrf: no token


def test_failed_requests_lock_server(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING), serving(settings=PageSettings(max_failed_requests=3)) as page:
        client, app = page.client, page.app
        token = client.token("/request/req-1")
        good = {**FORM, CSRF_FIELD: token}
        for _ in range(5):  # unknown paths and methods are not security failures
            assert client.get("/nowhere").status == 404
            assert client.request("PUT", "/").status == 405
        assert client.get("/").status == 200
        assert _refuse(client, "host") >= 400
        assert _refuse(client, "origin") >= 400
        assert client.get("/").status == 200  # two of three: still serving
        assert client.post("/answer/req-1", good).status == 200
        assert _refuse(client, "csrf") >= 400  # the third
        launch = urlsplit(page.server.launch_address)
        for path in ("/", "/report", "/request/req-1", "/setup/setup-1", "/nowhere", f"{launch.path}?{launch.query}"):
            result = client.get(path)
            assert result.status == 503, path
            assert RUN_DATA not in result.body
        assert client.post("/answer/req-1", good).status == 503
        assert len(app.submitted) == 1  # nothing after the lockdown reached the application
        warned = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warned
        secrets = [page.server.launch_address.partition("code=")[2], (client.cookie or "").partition("=")[2], token]
        assert not any(secret in caplog.text for secret in secrets)


@pytest.mark.parametrize("kind", ["host", "origin", "fetch-site", "cookie", "launch-code", "csrf"])
def test_each_security_refusal_counts(kind: str) -> None:
    with serving(settings=PageSettings(max_failed_requests=1)) as page:
        assert _refuse(page.client, kind) >= 400
        assert page.client.get("/").status == 503


def test_shutdown_releases_port() -> None:
    with serving() as page:
        port = page.server.port
        assert page.server.running
        assert page.client.get("/").status == 200
    assert not page.server.running
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection(("127.0.0.1", port), timeout=5)
    page.server.close()  # closing twice is harmless


def test_a_server_that_was_never_started_frees_its_port_on_close() -> None:
    server = PageServer(StubApp())
    assert not server.running
    port = server.port
    server.close()
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection(("127.0.0.1", port), timeout=5)
