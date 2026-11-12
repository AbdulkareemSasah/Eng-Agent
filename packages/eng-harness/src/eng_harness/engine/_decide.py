"""Decisions of the engine: `ctx.decide` and `ctx.decide_many` over the DecisionPort (spec 0001 4.3.2, 4.9.1).

Purpose: the options must be a `StrEnum` or references and the answer one of them (invariant 4, AC40), so no number
reaches the block. A `PendingAnswer` is one `engine.decision` input request (a batch is one request, its id the
`batch_id`); the answer goes back to the port as an `EngineerChoice` (AC66). Units: none. Errors: `BlockRuleViolation`,
`DecisionInvalid`, `AwaitingInput` (no usable answer yet), `ContractError` `INTERNAL` (no port, or no question).
"""

import functools
import hashlib
import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import Clock, IdSource
from eng_contract.refs import Ref
from pydantic import BaseModel, JsonValue, ValidationError

from eng_harness import errors
from eng_harness.ctx import BasisView, Decision, DecisionRequest
from eng_harness.decisions._points import DecisionPoint, PointRegistry, discover
from eng_harness.engine._inputs import Evidence, Question, build_request, check_answer, choice_schema
from eng_harness.journal import Event, EventType, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import (
    DecisionAnswer,
    DecisionCall,
    DecisionPort,
    EngineerChoice,
    InputPort,
    InputRequest,
    PendingAnswer,
)

_LOG = logging.getLogger(__name__)
_INDEX = re.compile(r"0|[1-9][0-9]*")
_Options = type[StrEnum] | tuple[Ref, ...]
type Settled = tuple[DecisionCall, DecisionAnswer, str | None]  # the call, its answer, the engineer's request id


class AwaitingInput(errors.Pause):
    """The run waits for the engineer's choice: `run_paused` with the reason `awaiting_input`."""


@functools.cache
def points() -> PointRegistry:
    """The decision points of the shipped workflows (`decisions._points.discover`), found once."""
    return discover()


@dataclass(frozen=True)
class Checked:
    """A request whose options and point passed the engine's checks."""

    request: DecisionRequest
    point: DecisionPoint
    options: _Options


def check(request: DecisionRequest) -> Checked:
    """Invariant 4 on the way in: `StrEnum` or references as options, a registered point (`BlockRuleViolation`)."""
    options = request.options
    if isinstance(options, type) and issubclass(options, StrEnum):
        kept: _Options = options
    elif isinstance(options, Sequence) and not isinstance(options, str) and all(isinstance(o, Ref) for o in options):
        kept = tuple(options)
    else:
        raise errors.BlockRuleViolation("decision options must be a StrEnum or a sequence of references")
    if (point := points().get(request.question)) is None:
        raise errors.BlockRuleViolation(f"{request.question!r} is not a registered decision point")
    return Checked(request, point, kept)


def values(options: _Options) -> list[str]:
    """The option values: the members' values, or the reference strings."""
    return [str(m.value) for m in options] if isinstance(options, type) else [r.ref for r in options]


def arguments(items: Sequence[Checked]) -> dict[str, JsonValue]:
    """What a decision step is matched on at replay: question, option values and state of each request."""
    wanted: list[JsonValue] = [
        {
            "question": i.request.question, "options": cast(JsonValue, values(i.options)),
            "state": i.request.state.model_dump(mode="json"),
        }
        for i in items
    ]  # fmt: skip
    return {"requests": wanted}


def _held(value: object) -> object:
    """`value` with its models opened into mappings, so that the references in it can be walked (invariant 3)."""
    if isinstance(value, BaseModel) and not isinstance(value, Ref):
        return {name: _held(getattr(value, name)) for name in type(value).model_fields}
    return [_held(item) for item in value] if isinstance(value, tuple | list) else value


def held(items: Sequence[Checked]) -> dict[str, object]:
    """The options and states, opened, by request, for the staleness check of invariant 3."""
    return {f"requests[{n}]": _held([i.options, i.request.state]) for n, i in enumerate(items)}


def pick(options: _Options, choice: str) -> StrEnum | Ref:
    """The member or reference that `choice` names (a value, or an index); `DecisionInvalid` if it is none."""
    if isinstance(options, type):
        try:
            return options(choice)
        except ValueError:
            raise errors.DecisionInvalid(f"{choice!r} is not an option of {options.__name__}") from None
    if _INDEX.fullmatch(choice) and int(choice) < len(options):
        return options[int(choice)]
    raise errors.DecisionInvalid(f"{choice!r} is not an index into {len(options)} references")


def decisions(items: Sequence[Checked], recorded: Sequence[Mapping[str, JsonValue]]) -> list[Decision[Any]]:
    """The block's decisions from the recorded `choice`, `decided_by` and `confidence` of each request."""
    return [
        Decision(
            choice=pick(i.options, str(r["choice"])), decided_by=str(r["decided_by"]),
            confidence=cast("float | None", r["confidence"]),
        )
        for i, r in zip(items, recorded, strict=True)
    ]  # fmt: skip


def made(call: DecisionCall, answer: DecisionAnswer, request_id: str | None) -> dict[str, JsonValue]:
    """The `decision_made` payload; `request_id` names the engineer's request, `None` for any other tier."""
    return {
        "point": call.point.name, "options": list(answer.options), "choice": answer.choice,
        "decided_by": answer.decided_by, "confidence": answer.confidence, "latency_ms": answer.latency_ms,
        "state_sha256": answer.state_sha256, "request_id": request_id,
        "suggestions": [s.model_dump(mode="json", by_alias=True) for s in answer.suggestions],
    }  # fmt: skip


def _text(value: JsonValue) -> str:
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True)


class Decider:
    """The ports and journal a run's decisions work with."""

    def __init__(
        self, port: DecisionPort | None, inputs: InputPort, basis: Callable[[], BasisView],
        journal: Callable[[], list[Event]], writer: JournalWriter, clock: Clock, ids: IdSource, run_id: str,
        events: Sequence[Event],
    ) -> None:  # fmt: skip
        """Serve one run; `basis` builds its `BasisView`, `journal` reads the journal so far, `events` are replayed."""
        self._port, self._inputs, self._basis, self._journal = port, inputs, basis, journal
        self._writer, self._clock, self._ids, self._run_id = writer, clock, ids, run_id
        self._requested = {e.payload.request_id for e in events if isinstance(e.payload, ev.InputRequested)}

    def _sensitive(self) -> tuple[str, ...]:
        """The base names of the model files the run touches, from the journal so far (spec 4.9.1, AC66)."""
        names: dict[str, None] = {}
        for event in self._journal():
            if isinstance(event.payload, ev.ModelBound):
                names.update(dict.fromkeys(event.payload.file_names))
            elif isinstance(event.payload, ev.ModelSaved):
                names.update(dict.fromkeys([*event.payload.origin_file_names, event.payload.file_name]))
        return tuple(names)

    def _calls(self, path: str, items: Sequence[Checked], *, many: bool) -> list[DecisionCall]:
        names, view, calls = self._sensitive(), self._basis(), []
        for n, item in enumerate(items):
            key = f"{path}/{n}" if many else path  # the id of call n of a batch takes the index (spec 4.9.1)
            digest = hashlib.sha256(f"{self._run_id}\n{key}".encode()).hexdigest()
            options = item.options if isinstance(item.options, type) else tuple(values(item.options))
            try:
                calls.append(DecisionCall.model_validate({
                    "request_id": "dec_" + digest[:32], "run_id": self._run_id, "step_path": path,
                    "point": item.point, "options": options, "state": item.request.state,
                    "rules": tuple(item.request.rules), "policy": item.request.policy, "basis": view,
                    "sensitive_values": names,
                }))  # fmt: skip
            except ValidationError as exc:
                raise errors.BlockRuleViolation(
                    "a decision needs a model as state, Rules and a DecisionPolicy"
                ) from exc
        return calls

    @staticmethod
    async def _ask(
        port: DecisionPort, calls: Sequence[DecisionCall], many: bool
    ) -> list[DecisionAnswer | PendingAnswer]:
        return list(await port.decide_many(calls)) if many else [await port.decide(calls[0])]

    async def settle(self, path: str, items: Sequence[Checked], *, many: bool) -> list[Settled]:
        """Decide each request in order; a pending call goes to the engineer, then the port is asked again (AC66).

        Raises `AwaitingInput` for no answer or a refused one, `ContractError` `INTERNAL` for no port.
        """
        if self._port is None:
            raise ContractError(ErrorCode.INTERNAL, "no DecisionPort is configured", incident_id=self._ids.new_ulid())
        calls = self._calls(path, items, many=many)
        port, rid = self._port, None
        got = await self._ask(port, calls, many)
        asked = [n for n, a in enumerate(got) if isinstance(a, PendingAnswer)]
        if asked:
            request = await self._present([a for a in got if isinstance(a, PendingAnswer)])
            rid, (choices, by) = request.request_id, await self._choices(request)
            made_by, now = by.removeprefix("engineer:"), self._clock.now()
            picks = [calls[n].model_copy(update={"engineer_choice": EngineerChoice(
                choice=choices[calls[n].request_id], by=made_by, answered_at=now
            )}) for n in asked]  # fmt: skip
            for n, again in zip(asked, await self._ask(port, picks, many), strict=True):
                if isinstance(again, PendingAnswer):  # the cascade refused the choice: the same request, again
                    await self._present([again])
                    raise AwaitingInput(f"decision request {rid} awaits the engineer", evidence=[rid])
                got[n] = again
        done = zip(calls, got, strict=True)
        return [(c, a, rid if n in asked else None) for n, (c, a) in enumerate(done) if isinstance(a, DecisionAnswer)]

    async def _choices(self, request: InputRequest) -> tuple[dict[str, str], str]:
        """The choices the engineer made for `request` and who made them; `AwaitingInput` when there are none."""
        answer = await self._inputs.answer(request.request_id, wait=False)
        try:
            if answer is not None:
                check_answer(request, answer)
        except ContractError as refused:  # the request stays open, as for any answer that does not fit (4.9.1)
            _LOG.warning("the answer to %s is refused and the request stays open: %s", request.request_id, refused)
            answer = None
        if answer is None or answer.choices is None:
            message = f"decision request {request.request_id} awaits the engineer"
            raise AwaitingInput(message, evidence=[request.request_id])
        return dict(answer.choices), answer.by

    async def _present(self, pending: Sequence[PendingAnswer]) -> InputRequest:
        """Build the `engine.decision` request of `pending`, journal `input_requested` once and present it."""
        items = list({i.request_id: i for p in pending for i in p.screen.items}.values())
        if not {p.request_id for p in pending} <= {i.request_id for i in items}:
            message = "a pending decision has no item on its screen"
            raise ContractError(ErrorCode.INTERNAL, message, incident_id=self._ids.new_ulid())
        questions = [
            Question(name=i.request_id, prompt=i.title, options=tuple(o.value for o in i.options)) for i in items
        ]
        shown = [
            Evidence(name=f"{i.request_id}_{n}", label=f.label, text=_text(f.value))
            for i in items for n, f in enumerate(i.fields) if f.ref is None
        ]  # fmt: skip
        refs = [f.ref for i in items for f in i.fields if f.ref is not None]
        title = items[0].title if len(items) == 1 else f"{len(items)} decisions"
        rid = pending[0].batch_id or pending[0].request_id
        request = build_request(self._ids, rid, "engine.decision", title, choice_schema(questions, shown), refs)
        if rid not in self._requested:
            sha = request.fields_schema_sha256
            body = {"request_id": rid, "kind": request.kind, "title": title, "fields_schema_sha256": sha}
            self._writer.append(EventType.INPUT_REQUESTED, body)
            self._requested.add(rid)
        await self._inputs.present(request)
        return request
