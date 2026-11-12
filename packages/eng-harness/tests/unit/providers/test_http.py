"""Shared HTTP client (spec 0009 section 4.5; AC9 to AC11, AC14, AC15). Nothing here reaches the network."""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Coroutine
from pathlib import Path

import httpx2
import pytest
from fakes.credential_stores import FakeCredentialStore
from pydantic import JsonValue, SecretStr

from eng_harness.decisions.interfaces import ProviderError, ProviderErrorCode
from eng_harness.providers._config import LLMProviderConfig
from eng_harness.providers._http import ProviderClient

from ._leaks import assert_no_leak

KEY = "-".join(("sk", "sentinel", "key", "0042"))
REMOTE = "remote-diagnostic-text"  # what a remote service says in an error body
LOCAL_BODY = "request-body-marker"  # what the request carries
PATH = "chat/completions"
Handler = (
    Callable[[httpx2.Request], httpx2.Response] | Callable[[httpx2.Request], Coroutine[None, None, httpx2.Response]]
)
SyncHandler = Callable[[httpx2.Request], httpx2.Response]


def _config(**changes: object) -> LLMProviderConfig:
    fields: dict[str, object] = {
        "name": "llm",
        "base_url": "https://api.example.test/v1",
        "model": "vendor/model",
        "model_version": "1",
        "key_ref": "llmkey",
        "request_timeout_ms": 1000,
        "max_output_tokens": 50,
        **changes,
    }
    return LLMProviderConfig.model_validate(fields)


def _store(key: str | None = KEY) -> FakeCredentialStore:
    store = FakeCredentialStore()
    if key is not None:
        store.set("llmkey", SecretStr(key))
    return store


async def _call(
    handler: Handler,
    *,
    config: LLMProviderConfig | None = None,
    store: FakeCredentialStore | None = None,
    sensitive: tuple[str, ...] = (),
) -> dict[str, JsonValue]:
    client = ProviderClient(config or _config(), store or _store(), transport=httpx2.MockTransport(handler))
    try:
        return await client.post_json(PATH, {"point": "p", "state": {"note": LOCAL_BODY}}, sensitive_values=sensitive)
    finally:
        await client.aclose()


def _ok(_: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, json={"ok": True})


def test_key_only_in_authorization_header(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"ok": True})

    assert asyncio.run(_call(handler)) == {"ok": True}
    assert len(seen) == 1
    request = seen[0]
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert request.method == "POST"
    assert str(request.url) == "https://api.example.test/v1/chat/completions"
    for name, value in request.headers.items():
        if name.lower() != "authorization":
            assert KEY not in value
    assert KEY not in str(request.url)
    assert KEY not in request.content.decode()
    assert KEY not in caplog.text


def test_error_mapping() -> None:
    def raising(exc: Callable[[httpx2.Request], Exception]) -> SyncHandler:
        def handler(request: httpx2.Request) -> httpx2.Response:
            raise exc(request)

        return handler

    async def slow(_: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(2)
        return httpx2.Response(200, json={})

    def status(code: int, headers: dict[str, str] | None = None) -> SyncHandler:
        return lambda _: httpx2.Response(code, text=REMOTE, headers=headers)

    cases: list[tuple[Handler, ProviderErrorCode]] = [
        (raising(lambda r: httpx2.ConnectError(f"{REMOTE} {KEY}", request=r)), ProviderErrorCode.NETWORK),
        (raising(lambda r: httpx2.ReadTimeout(REMOTE, request=r)), ProviderErrorCode.TIMEOUT),
        (slow, ProviderErrorCode.TIMEOUT),
        (status(401), ProviderErrorCode.AUTH),
        (status(403), ProviderErrorCode.AUTH),
        (status(429, headers={"Retry-After": "30"}), ProviderErrorCode.RATE_LIMITED),
        (status(404), ProviderErrorCode.HTTP_STATUS),
        (status(500), ProviderErrorCode.HTTP_STATUS),
        (status(302, headers={"Location": "https://other.example.test/"}), ProviderErrorCode.HTTP_STATUS),
        (lambda _: httpx2.Response(200, text=REMOTE), ProviderErrorCode.BAD_RESPONSE),
        (lambda _: httpx2.Response(200, content=b"\xff\xfe"), ProviderErrorCode.BAD_RESPONSE),
        (lambda _: httpx2.Response(200, json=[REMOTE]), ProviderErrorCode.BAD_RESPONSE),
    ]
    for handler, code in cases:
        with pytest.raises(ProviderError) as excinfo:
            asyncio.run(_call(handler, config=_config(request_timeout_ms=100)))
        assert excinfo.value.code is code
        assert str(excinfo.value) == code.value
        assert excinfo.value.__cause__ is None
        assert excinfo.value.__context__ is None
        assert_no_leak(excinfo.value, (KEY,), (REMOTE,))


def test_one_request_no_retry_no_redirect() -> None:
    for code in (200, 302, 429, 500, 503):
        calls: list[httpx2.Request] = []

        def handler(request: httpx2.Request, code: int = code, calls: list[httpx2.Request] = calls) -> httpx2.Response:
            calls.append(request)
            return httpx2.Response(
                code, json={"ok": True}, headers={"Retry-After": "5", "Location": "https://other.example.test/"}
            )

        started = time.monotonic()
        with contextlib.suppress(ProviderError):
            asyncio.run(_call(handler))
        assert len(calls) == 1
        assert time.monotonic() - started < 1.0  # no Retry-After wait


def test_no_secret_or_body_in_logs_or_errors(caplog: pytest.LogCaptureFixture) -> None:
    names = ("openai", "httpx2", "httpcore2", "pydantic_ai")
    for name in names:
        logging.getLogger(name).setLevel(logging.DEBUG)  # the client builder must raise this
    caplog.set_level(logging.DEBUG)

    def failing(code: int) -> SyncHandler:
        return lambda _: httpx2.Response(code, text=REMOTE)

    def boom(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError(f"{REMOTE} {KEY}", request=request)

    errors: list[ProviderError] = []
    for handler in (failing(401), failing(429), failing(500), boom):
        with pytest.raises(ProviderError) as excinfo:
            asyncio.run(_call(handler))
        errors.append(excinfo.value)
    assert asyncio.run(_call(_ok)) == {"ok": True}
    for name in names:
        assert logging.getLogger(name).level >= logging.WARNING
    text = "\n".join(f"{r.getMessage()}\n{r.exc_text or ''}" for r in caplog.records)
    for secret in (KEY, REMOTE, LOCAL_BODY, "Bearer"):
        assert secret not in text
    assert "HTTP Request" not in text
    for error in errors:
        assert_no_leak(error, (KEY,), (REMOTE,))


def test_missing_key() -> None:
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(200, json={"ok": True})

    with pytest.raises(ProviderError) as stored:
        asyncio.run(_call(handler, store=_store(None)))
    assert stored.value.code is ProviderErrorCode.NO_KEY
    unnamed = _config().model_copy(update={"key_ref": None})  # a non-local provider without key_ref
    with pytest.raises(ProviderError) as nameless:
        asyncio.run(_call(handler, config=unnamed))
    assert nameless.value.code is ProviderErrorCode.NO_KEY
    local = _config(base_url="http://127.0.0.1:8080/v1", local=True, key_ref=None)
    assert asyncio.run(_call(handler, config=local)) == {"ok": True}
    assert "authorization" not in calls[0].headers  # the only request so far
    assert len(calls) == 1
    local_named = _config(base_url="http://127.0.0.1:8080/v1", local=True)
    with pytest.raises(ProviderError) as missing:
        asyncio.run(_call(handler, config=local_named, store=_store(None)))
    assert missing.value.code is ProviderErrorCode.NO_KEY
    assert len(calls) == 1


def test_trust_env_is_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    netrc = tmp_path / "netrc"
    netrc.write_text("machine api.example.test login other password other-secret\n", encoding="utf-8")
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    monkeypatch.setenv("NETRC", str(netrc))
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "missing.pem"))
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"ok": True})

    client = ProviderClient(_config(), _store(), transport=httpx2.MockTransport(handler))
    assert client.http.trust_env is False
    assert asyncio.run(client.post_json(PATH, {"point": "p"})) == {"ok": True}
    assert len(seen) == 1
    assert str(seen[0].url) == "https://api.example.test/v1/chat/completions"
    assert seen[0].headers["Authorization"] == f"Bearer {KEY}"
