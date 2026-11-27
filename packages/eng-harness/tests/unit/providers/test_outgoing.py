"""Outgoing guard (spec 0009 section 4.5; AC12, AC13): the last check before a byte leaves the machine."""

import asyncio
import json
from collections.abc import Mapping, Sequence

import httpx2
import pytest
from fakes.credential_stores import FakeCredentialStore
from pydantic import JsonValue, SecretStr

from eng_harness.decisions.interfaces import (
    OutgoingPlace,
    ProviderError,
    ProviderErrorCode,
    ProviderOption,
    ProviderRequest,
)
from eng_harness.providers._config import LLMProviderConfig
from eng_harness.providers._http import ProviderClient
from eng_harness.providers._outgoing import guard_request

KEY = "-".join(("sk", "sentinel", "key", "0042"))
PATH = "chat/completions"


def _client(calls: list[httpx2.Request]) -> ProviderClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(200, json={"ok": True})

    config = LLMProviderConfig(
        name="llm",
        base_url="https://api.example.test/v1",
        model="vendor/model",
        model_version="1",
        key_ref="llmkey",
        request_timeout_ms=1000,
        max_output_tokens=50,
    )
    store = FakeCredentialStore()
    store.set("llmkey", SecretStr(KEY))
    return ProviderClient(config, store, transport=httpx2.MockTransport(handler))


def _post(body: Mapping[str, JsonValue], sensitive: Sequence[str]) -> list[httpx2.Request]:
    calls: list[httpx2.Request] = []

    async def run() -> None:
        client = _client(calls)
        try:
            await client.post_json(PATH, body, sensitive_values=sensitive)
        finally:
            await client.aclose()

    asyncio.run(run())
    return calls


def _blocked(body: Mapping[str, JsonValue], sensitive: Sequence[str]) -> OutgoingPlace | None:
    calls: list[httpx2.Request] = []

    async def run() -> None:
        client = _client(calls)
        try:
            await client.post_json(PATH, body, sensitive_values=sensitive)
        finally:
            await client.aclose()

    with pytest.raises(ProviderError) as excinfo:
        asyncio.run(run())
    assert excinfo.value.code is ProviderErrorCode.REDACTION_BLOCKED
    assert str(excinfo.value) == "redaction_blocked"
    assert calls == []  # zero requests
    return excinfo.value.where


def _chat(data: object) -> dict[str, JsonValue]:
    """A body in the chat shape: the data block is embedded as a JSON string in the user message."""
    return {"messages": [{"role": "user", "content": json.dumps(data)}]}


def test_final_body_scan() -> None:
    needle = "Acme Tower"
    assert _blocked({"point": f"see {needle}"}, [needle]) is OutgoingPlace.STATE_VALUE
    assert _blocked({"point": "ACME TOWER"}, [needle]) is OutgoingPlace.STATE_VALUE  # case folding
    assert _blocked(_chat({"state": {"note": f"x {needle} y"}}), [needle]) is OutgoingPlace.STATE_VALUE
    assert _blocked(_chat({"state": {"note": json.dumps({"deep": needle})}}), [needle]) is OutgoingPlace.STATE_VALUE
    decomposed = "Gebäude Süd"  # a-umlaut and u-umlaut written as base letter plus combining mark
    assert _blocked({"label": "x GEBÄUDE SÜD"}, ["Gebäude Süd"]) is OutgoingPlace.STATE_VALUE  # NFC
    assert _blocked({"label": decomposed}, ["Gebäude Süd"]) is OutgoingPlace.STATE_VALUE
    tricky = 'say "hi" \\ there'  # quotes and a backslash are escaped in transit
    assert _blocked(_chat({"state": {"note": tricky}}), [tricky]) is OutgoingPlace.STATE_VALUE
    assert _blocked({"label": "ünï 日本語"}, ["ünï 日本語"]) is OutgoingPlace.STATE_VALUE
    assert _blocked({"headers": f"token {KEY}"}, []) is OutgoingPlace.KEY_MATERIAL
    assert _blocked(_chat({"state": {"note": KEY}}), []) is OutgoingPlace.KEY_MATERIAL
    # a value shorter than 3 characters is ignored, and a clean body goes out once
    assert len(_post({"point": "ab"}, ["ab"])) == 1
    assert len(_post({"point": "fine"}, [needle, "ab"])) == 1
    assert len(_post({"point": "exactly"}, ["abc", "xyz"])) == 1
    assert _blocked({"point": "xabcx"}, ["abc"]) is OutgoingPlace.STATE_VALUE  # three characters count


def test_object_keys_are_scanned() -> None:
    needle = "Acme Tower"
    assert _blocked({needle: 1}, [needle]) is OutgoingPlace.STATE_KEY
    assert _blocked({"state": {"a": {"b": [{"acme tower": 1}]}}}, [needle]) is OutgoingPlace.STATE_KEY
    assert _blocked(_chat({"state": {"a": {needle: 1}}}), [needle]) is OutgoingPlace.STATE_KEY  # embedded block
    assert _blocked({KEY: 1}, []) is OutgoingPlace.KEY_MATERIAL
    assert len(_post({"state": {"clean": {"keys": 1}}}, [needle])) == 1


def _request(
    *,
    point: str = "footing_fix",
    options: tuple[ProviderOption, ...] = (ProviderOption(value="a", label="Enlarge"),),
    state: Mapping[str, JsonValue] | None = None,
) -> ProviderRequest:
    return ProviderRequest(
        request_id="dec_1", point=point, point_version=1, options=options, state=state or {"governing": "bearing"}
    )


def test_adapter_rechecks_state() -> None:
    needle = "Acme Tower"
    guard_request(_request(), [needle])  # clean: no error
    guard_request(_request(state={"note": "ab"}), ["ab"])  # shorter than 3 characters

    def place(request: ProviderRequest, sensitive: Sequence[str] = (needle,)) -> OutgoingPlace | None:
        with pytest.raises(ProviderError) as excinfo:
            guard_request(request, sensitive)
        assert excinfo.value.code is ProviderErrorCode.REDACTION_BLOCKED
        assert str(excinfo.value) == "redaction_blocked"
        return excinfo.value.where

    assert place(_request(state={"note": "near acme tower"})) is OutgoingPlace.STATE_VALUE
    assert place(_request(state={"a": {"b": [{"ACME TOWER": 1}]}})) is OutgoingPlace.STATE_KEY
    assert place(_request(point="acme tower fix")) is OutgoingPlace.POINT
    assert place(_request(options=(ProviderOption(value="Acme Tower", label="x"),))) is OutgoingPlace.OPTION_VALUE
    assert place(_request(options=(ProviderOption(value="a", label="the Acme Tower"),))) is OutgoingPlace.OPTION_LABEL
    # the redaction check of spec 0005 section 4.10 runs even with no sensitive value: a path, a URL, an address
    assert place(_request(state={"note": "C:/work/model.edb"}), ()) is OutgoingPlace.STATE_VALUE
    assert place(_request(state={"note": "https://example.test/x"}), ()) is OutgoingPlace.STATE_VALUE
    assert place(_request(state={"note": "someone@example.test"}), ()) is OutgoingPlace.STATE_VALUE
    # called directly, then sent: the guard stops the call before the transport
    calls: list[httpx2.Request] = []

    async def adapter(request: ProviderRequest) -> None:
        guard_request(request, [needle])
        client = _client(calls)
        try:
            await client.post_json(PATH, {"point": request.point}, sensitive_values=[needle])
        finally:
            await client.aclose()

    with pytest.raises(ProviderError):
        asyncio.run(adapter(_request(state={"note": "Acme Tower"})))
    assert calls == []
    asyncio.run(adapter(_request()))
    assert len(calls) == 1
