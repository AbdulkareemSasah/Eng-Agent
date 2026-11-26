"""Jev adapter tests for spec 0009 §3.4 and §4.6, using synthetic wire formats."""

import ast
import asyncio
import json
import re
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Literal, NoReturn, cast

import httpx2
import pytest
from eng_contract.errors import ContractError, ErrorCode
from fakes.credential_stores import FakeCredentialStore
from fakes.jev_formats import CallFactory, FlatFormat, NestedFormat, Operation, ParsedAnswer

from eng_harness.decisions.interfaces import (
    ChoiceAnswer,
    DecisionProvider,
    ProviderError,
    ProviderErrorCode,
    ProviderFailure,
    ProviderInfo,
    ProviderOption,
    ProviderRequest,
    YesNoAnswer,
)
from eng_harness.providers import _http
from eng_harness.providers._config import DecisionProviderConfig
from eng_harness.providers._credentials import KeyringCredentialStore
from eng_harness.providers._http import ProviderClient

_ADAPTER = "eng_harness.providers._jev"
_FORMAT = "eng_harness.providers._jev_format"
_BASE_URL = "http://127.0.0.1"
_CONFIG = DecisionProviderConfig(
    name="synthetic",
    model="fixture-model",
    model_version="fixture",
    base_url=_BASE_URL,
    local=True,
    request_timeout_ms=1000,
)
type _FakeFormat = FlatFormat[object] | NestedFormat[object]
type _Handler = Callable[[httpx2.Request], httpx2.Response]


def _feature(name: str) -> ModuleType:
    try:
        return import_module(name)
    except ModuleNotFoundError as error:
        if error.name != name:
            raise
    pytest.fail(f"T4 Jev feature module is missing: {name}", pytrace=False)


def _call_factory() -> CallFactory[object]:
    return cast(CallFactory[object], _feature(_FORMAT).HttpCall)


def _request(request_id: str, *values: str) -> ProviderRequest:
    return ProviderRequest(
        request_id=request_id,
        point="fixture",
        point_version=1,
        state={},
        options=tuple(ProviderOption(value=value, label=value) for value in values),
    )


@asynccontextmanager
async def _provider(format_: _FakeFormat, handle: _Handler) -> AsyncIterator[DecisionProvider]:
    adapter = cast(
        Callable[[DecisionProviderConfig, ProviderClient, _FakeFormat], DecisionProvider],
        _feature(_ADAPTER).JevProvider,
    )
    client = ProviderClient(_CONFIG, FakeCredentialStore(), transport=httpx2.MockTransport(handle))
    try:
        yield adapter(_CONFIG, client, format_)
    finally:
        await client.aclose()


async def _invoke(
    provider: DecisionProvider, op: Operation, requests: Sequence[ProviderRequest]
) -> ParsedAnswer | Sequence[ChoiceAnswer | ProviderFailure]:
    match op:
        case "choose":
            return await provider.choose(requests[0])
        case "yes_no":
            return await provider.yes_no(requests[0])
        case "score":
            return await provider.score(requests[0])
        case "batch":
            return await provider.batch(requests)


async def _exchange(
    format_: _FakeFormat, op: Operation, requests: Sequence[ProviderRequest]
) -> ParsedAnswer | Sequence[ChoiceAnswer | ProviderFailure]:
    ids = [request.request_id for request in requests]
    if isinstance(format_, FlatFormat):
        path = "/flat/decide"
        outgoing: object = {"verb": op, "tokens": ids}
        incoming: object = {"receipt": op, "echo": ids}
    else:
        path = "/nested/infer"
        outgoing = {"packet": {"action": op, "items": [{"tag": value} for value in ids]}}
        incoming = {"reply": {"action": op, "items": [{"tag": value} for value in ids]}}
    seen: list[tuple[str, str, object]] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append((request.method, str(request.url), json.loads(request.content)))
        return httpx2.Response(200, json=incoming)

    async with _provider(format_, handle) as provider:
        try:
            result = await _invoke(provider, op, requests)
        finally:
            assert seen == [("POST", _BASE_URL + path, outgoing)]
    return result


async def _check_operations(shape: Literal["flat", "nested"]) -> None:
    factory = _call_factory()
    request = _request("first", "alpha", "beta")
    choice = ChoiceAnswer(choice="beta", confidence=1.0)
    yes_no = YesNoAnswer(answer=False, confidence=0.0)
    scores = {"alpha": 0.0, "beta": 1.0}
    cases: tuple[tuple[Operation, ParsedAnswer], ...] = (
        ("choose", choice),
        ("yes_no", yes_no),
        ("score", scores),
        ("batch", choice),
    )
    for op, answer in cases:
        format_ = FlatFormat(factory, [answer]) if shape == "flat" else NestedFormat(factory, [answer])
        result = await _exchange(format_, op, [request])
        if op == "batch":
            assert isinstance(result, Sequence)
            assert tuple(result) == (answer,)
        else:
            assert result == answer


def _unexpected_io(*args: object, **kwargs: object) -> NoReturn:
    pytest.fail("This operation must not create a client, read a key, or send a request")


def test_formats_not_implemented_until_s07(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_http, "build_http_client", _unexpected_io)
    monkeypatch.setattr(KeyringCredentialStore, "get", _unexpected_io)
    select_format = _feature(_FORMAT).select_format
    for backend in ("openrouter", "typesafe"):
        with pytest.raises(ProviderError, match="S-07") as exc:
            select_format(backend)
        assert exc.value.code is ProviderErrorCode.NOT_IMPLEMENTED
        assert exc.value.gap == "J-G1"


def test_operations_go_through_the_format() -> None:
    asyncio.run(_check_operations("flat"))

    async def refuse_non_post() -> None:
        format_ = FlatFormat(_call_factory(), [], method="GET")
        request = _request("first", "alpha", "beta")
        async with _provider(format_, _unexpected_io) as provider:
            with pytest.raises(ContractError) as exc:
                await provider.choose(request)
            assert exc.value.detail.code is ErrorCode.INVALID_ARGUMENT

    asyncio.run(refuse_non_post())


def test_second_format_needs_no_adapter_change() -> None:
    asyncio.run(_check_operations("nested"))


def test_wire_knowledge_is_in_one_module() -> None:
    module = _feature(_ADAPTER)
    assert module.__file__ is not None
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    literals = {
        node.value.casefold()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert literals.isdisjoint({"verb", "tokens", "receipt", "echo", "packet", "action", "items", "tag", "reply"})
    assert all("openrouter" not in value and "typesafe" not in value for value in literals)
    assert all(re.fullmatch(r"/?[a-z][\w.-]*(?:/[a-z][\w.-]*)+/?", value) is None for value in literals)


def test_answer_validation() -> None:
    async def check() -> None:
        factory = _call_factory()
        request = _request("first", "alpha", "beta")
        cases: list[tuple[Operation, ParsedAnswer]] = [
            ("choose", ChoiceAnswer(choice="other", confidence=1.0)),
            ("score", {"alpha": 0.0}),
            ("score", {"alpha": 0.0, "beta": 1.0, "other": 0.0}),
        ]
        # A format can return a typed result without passing through Pydantic validation.
        for confidence in (-1.0, 2.0, float("inf"), float("nan")):
            cases.append(("choose", ChoiceAnswer.model_construct(choice="alpha", confidence=confidence)))
            cases.append(("yes_no", YesNoAnswer.model_construct(answer=True, confidence=confidence)))
        for op, answer in cases:
            with pytest.raises(ProviderError) as exc:
                await _exchange(FlatFormat(factory, [answer]), op, [request])
            assert exc.value.code is ProviderErrorCode.INVALID_OUTPUT

    asyncio.run(check())


def test_batch_single_request() -> None:
    async def check() -> None:
        factory = _call_factory()
        requests = [
            _request("first", "alpha"),
            _request("second", "beta"),
            _request("third", "gamma"),
            _request("fourth", "delta"),
        ]
        first = ChoiceAnswer(choice="alpha", confidence=0.0)
        last = ChoiceAnswer(choice="delta", confidence=1.0)
        marked_failed = ProviderFailure(code=ProviderErrorCode.BAD_RESPONSE)
        invalid = ChoiceAnswer(choice="gamma", confidence=1.0)
        answers: list[ParsedAnswer] = [first, invalid, marked_failed, last]
        result = await _exchange(FlatFormat(factory, answers), "batch", requests)
        assert isinstance(result, Sequence)
        assert tuple(result) == (
            first,
            ProviderFailure(code=ProviderErrorCode.INVALID_OUTPUT),
            marked_failed,
            last,
        )
        for wrong_count in (answers[:-1], [*answers, last]):
            with pytest.raises(ProviderError) as exc:
                await _exchange(FlatFormat(factory, wrong_count), "batch", requests)
            assert exc.value.code is ProviderErrorCode.BAD_RESPONSE

    asyncio.run(check())


def test_provider_info() -> None:
    async def check() -> None:
        factory = _call_factory()
        flat = FlatFormat(factory, [], supports_batch=False)
        nested = NestedFormat(factory, [])
        async with _provider(flat, _unexpected_io) as provider:
            assert provider.info == ProviderInfo(
                provider="synthetic",
                model="fixture-model",
                version="fixture;map-1",
                is_local=True,
                supports_batch=False,
            )
        async with _provider(nested, _unexpected_io) as provider:
            assert provider.info == ProviderInfo(
                provider="synthetic",
                model="fixture-model",
                version="fixture;map-2",
                is_local=True,
                supports_batch=True,
            )

    asyncio.run(check())
