"""Synthetic Jev formats for spec 0009 §4.6. Neither shape represents a real backend."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import JsonValue

from eng_harness.decisions.interfaces import ChoiceAnswer, ProviderFailure, ProviderRequest, YesNoAnswer

type Operation = Literal["choose", "yes_no", "score", "batch"]
type ParsedAnswer = ChoiceAnswer | YesNoAnswer | Mapping[str, float] | ProviderFailure


class CallFactory[T](Protocol):
    def __call__(self, *, method: str, path: str, body: dict[str, JsonValue]) -> T: ...


@dataclass
class FlatFormat[T]:
    call: CallFactory[T]
    answers: Sequence[ParsedAnswer]
    method: str = "POST"
    revision: int = 1
    supports_batch: bool = True

    def build(self, op: Operation, requests: Sequence[ProviderRequest]) -> T:
        ids: list[JsonValue] = [request.request_id for request in requests]
        return self.call(method=self.method, path="flat/decide", body={"verb": op, "tokens": ids})

    def parse(self, op: Operation, requests: Sequence[ProviderRequest], body: JsonValue) -> list[ParsedAnswer]:
        assert body == {"receipt": op, "echo": [request.request_id for request in requests]}
        return list(self.answers)


@dataclass
class NestedFormat[T]:
    call: CallFactory[T]
    answers: Sequence[ParsedAnswer]
    revision: int = 2
    supports_batch: bool = True

    def build(self, op: Operation, requests: Sequence[ProviderRequest]) -> T:
        items: list[JsonValue] = [{"tag": request.request_id} for request in requests]
        return self.call(method="POST", path="nested/infer", body={"packet": {"action": op, "items": items}})

    def parse(self, op: Operation, requests: Sequence[ProviderRequest], body: JsonValue) -> list[ParsedAnswer]:
        assert body == {"reply": {"action": op, "items": [{"tag": request.request_id} for request in requests]}}
        return list(self.answers)
