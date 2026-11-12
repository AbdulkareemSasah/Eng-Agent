"""Sensitive text never reaches the transport (spec 0009 AC12), whatever its script, escaping or place."""

import asyncio
import json
import unicodedata

import httpx2
import pytest
from fakes.credential_stores import FakeCredentialStore
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import JsonValue, SecretStr

from eng_harness.decisions.interfaces import ProviderError, ProviderErrorCode, ProviderOption, ProviderRequest
from eng_harness.providers._config import LLMProviderConfig
from eng_harness.providers._http import ProviderClient
from eng_harness.providers._outgoing import guard_request

_TEXT = st.text(alphabet=st.characters(codec="utf-8"), min_size=3, max_size=12)
_PLACES = st.sampled_from(["state_value", "state_key", "point", "label", "value", "embedded"])


def _request(place: str, text: str) -> ProviderRequest:
    point, value, label = "footing_fix", "a", "Enlarge"
    state: dict[str, JsonValue] = {"governing": "bearing"}
    padded = f" {text} "
    if place == "state_value":
        state = {"outer": {"inner": [padded]}}
    elif place == "state_key":
        state = {"outer": [{padded: 1}]}
    elif place == "point":
        point = padded
    elif place == "label":
        label = padded
    elif place == "value":
        value = padded
    else:
        state = {"block": json.dumps({"x": padded})}
    return ProviderRequest(
        request_id="dec_1",
        point=point,
        point_version=1,
        options=(ProviderOption(value=value, label=label),),
        state=state,
    )


@settings(derandomize=True, max_examples=150, deadline=None)
@given(text=_TEXT, place=_PLACES, decomposed=st.booleans())
def test_sensitive_text_never_reaches_the_transport(text: str, place: str, decomposed: bool) -> None:
    calls: list[httpx2.Request] = []

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
    store.set("llmkey", SecretStr("-".join(("sk", "property", "key"))))
    request = _request(place, unicodedata.normalize("NFD", text) if decomposed else text)

    async def send() -> None:
        client = ProviderClient(config, store, transport=httpx2.MockTransport(handler))
        try:
            guard_request(request, [text])
            body: dict[str, JsonValue] = {"messages": [{"role": "user", "content": request.model_dump_json()}]}
            await client.post_json("chat/completions", body, sensitive_values=[text])
        finally:
            await client.aclose()

    with pytest.raises(ProviderError) as excinfo:
        asyncio.run(send())
    assert excinfo.value.code is ProviderErrorCode.REDACTION_BLOCKED
    assert calls == []
