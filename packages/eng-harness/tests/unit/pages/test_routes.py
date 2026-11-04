"""The route table, its methods and the limits on a request (plan 0006 T6; AC27; spec 0006 section 4.4.3)."""

import logging
import socket
from urllib.parse import urlencode

import pytest
from helpers.page_client import RUN_DATA, PageClient, serving

from eng_harness.pages import PageSettings
from eng_harness.pages._security import CSRF_FIELD
from eng_harness.pages._server import _Handler

LIMIT = 160  # bytes; the default of 32768 would need a large body in every test
FORM = {"decision": "approve", "reason": "ok"}


def _padded(token: str, size: int) -> bytes:
    """A valid urlencoded body of exactly `size` bytes."""
    base = len(urlencode({"decision": "a", CSRF_FIELD: token, "reason": ""}))
    return urlencode({"decision": "a", CSRF_FIELD: token, "reason": "r" * (size - base)}).encode()


def _post(client: PageClient, body: bytes, **headers: str | None) -> int:
    return client.request("POST", "/answer/req-1", body=body, headers=headers or None).status


def test_route_table_and_limits() -> None:
    with serving(settings=PageSettings(max_body_bytes=LIMIT, max_failed_requests=1000)) as page:
        client, app = page.client, page.app
        token = client.token("/request/req-1")
        good = {**FORM, CSRF_FIELD: token}

        for path in ("/", "/?x=1", "/report", "/request/req-1", "/request/req-2", "/setup/setup-1"):
            assert client.get(path).status == 200, path
        app.calls.clear()
        outside = ["/nowhere", "/request", "/request/", "/request/req-1/extra", "/setup/", "/report/", "/answer/"]
        outside += ["/request/" + "a" * 65, "/request/req%2D1", "/REQUEST/req-1", "/request/..", "/request/a.b"]
        outside += ["/static/app.css", "/favicon.ico", "/answer", "/index.html", "/launch/x"]
        for path in outside:  # not in the table, or an id outside [A-Za-z0-9_-]{1,64}: the app is never asked
            assert client.get(path).status == 404, path
        assert app.calls == []
        for path in ("/request/missing", "/setup/nope", "/request/" + "a" * 64, "/request/_", "/setup/-"):
            assert client.get(path).status == 404, path  # a well-formed id the app does not know
        assert app.calls == ["screen"] * 5
        assert client.post("/answer/missing", good).status == 404
        assert client.post("/setup/missing", good).status == 404

        for method, path in [("PUT", "/"), ("DELETE", "/report"), ("HEAD", "/"), ("OPTIONS", "/"), ("TRACE", "/")]:
            assert client.request(method, path).status == 405, (method, path)
        for method, path in [("PATCH", "/request/req-1"), ("POST", "/"), ("POST", "/report"), ("FOO", "/")]:
            assert client.request(method, path).status == 405, (method, path)
        for method, path in [("POST", "/request/req-1"), ("GET", "/answer/req-1"), ("POST", "/launch")]:
            assert client.request(method, path).status == 405, (method, path)
        assert client.request("DELETE", "/setup/setup-1").status == 405

        assert app.submitted == []
        assert _post(client, _padded(token, LIMIT)) == 200  # exactly the limit
        assert _post(client, _padded(token, LIMIT + 1)) == 413
        assert _post(client, b"", **{"Content-Length": "999999"}) == 413  # refused on the declared length
        assert len(app.submitted) == 1

        body = urlencode(good).encode()
        for media in (
            "text/plain",
            "application/json",
            "multipart/form-data; boundary=x",
            "application/x-www-form-urlencoded2",
            None,
        ):
            assert _post(client, body, **{"Content-Type": media}) == 415, media
        assert _post(client, body, **{"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}) == 200

        bodies = [
            urlencode({**good, "extra": "1"}),
            f"extra=1&{CSRF_FIELD}={token}",  # an unknown field among few
            urlencode(good) + "&reason=again",
            f"reason=a&reason=b&{CSRF_FIELD}={token}",  # a repeated field among few
            f"{CSRF_FIELD}={token}&{CSRF_FIELD}={token}",
        ]
        bodies += [urlencode(good) + "&decision", "&&", f"{CSRF_FIELD}={token}&reason"]
        for text in bodies:
            assert _post(client, text.encode()) == 400, text
        assert _post(client, f"{CSRF_FIELD}={token}&reason=".encode() + b"\xff") == 400  # not UTF-8
        for length in ("abc", "-1", "+5", "1.0", "", "\u00b2"):
            assert _post(client, body, **{"Content-Length": length}) == 400, length
        assert [(k, i) for k, i, _ in app.submitted] == [("request", "req-1")] * 2  # only the two accepted forms


def test_application_failure_is_500_without_detail(caplog: pytest.LogCaptureFixture) -> None:
    with serving() as page:
        failure = RuntimeError("secret detail of the run")
        page.app.failure = failure
        with caplog.at_level(logging.ERROR):
            result = page.client.get("/")
        assert result.status == 500
        assert "secret detail" not in result.body
        assert RUN_DATA not in result.body
        assert any(r.exc_info and r.exc_info[1] is failure for r in caplog.records)  # logged, not swallowed
        page.app.failure = None
        assert page.client.get("/").status == 200  # the server survives


def test_a_stalled_request_is_dropped_after_the_socket_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_Handler, "timeout", 1)  # seconds; the default would make the test wait for it
    with serving() as page:
        with socket.create_connection(("127.0.0.1", page.server.port), timeout=10) as stalled:
            stalled.sendall(b"POST /answer/req-1 HTTP/1.1\r\nHost: 127.0.0.1\r\n")  # the headers never end
            assert stalled.recv(1024) == b""  # the server closed the connection
        assert page.client.get("/").status == 200
