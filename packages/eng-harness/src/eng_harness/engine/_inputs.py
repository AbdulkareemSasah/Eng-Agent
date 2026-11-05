"""Input requests of the engine: the `x-eng-input` marker, choice schemas and answer checks (spec 0001 4.9.1, AC67).

Purpose: every request the engine presents is built here, so its schema says whether it holds data (`ctx.ask`, kind
`block`) or a choice (each `engine.*` kind), and an answer is checked against its request. Units: none. Errors:
`ContractError` `INTERNAL` for a schema built without the marker of its kind, `INVALID_ARGUMENT` for an answer that does
not fit (the request then stays open).
"""

from collections.abc import Mapping, Sequence
from typing import Literal

from eng_contract.canonical import payload_sha256
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import IdSource
from eng_contract.refs import RefString
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from eng_harness.decisions.types import Label
from eng_harness.journal import _events as ev
from eng_harness.ports import InputAnswer, InputRequest

MARKER = "x-eng-input"
Kind = Literal["block", "engine.in_flight", "engine.host_state", "engine.escalation", "engine.decision"]
_Schema = Mapping[str, JsonValue]
_EVIDENCE: _Schema = {"type": "string", "readOnly": True, "x-eng-evidence": True}


class Question(BaseModel):
    """One question of a choice request: a property `name`, its `prompt` (a `Label`) and its option values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    prompt: Label
    options: tuple[str, ...] = Field(min_length=1)

    @field_validator("options")
    @classmethod
    def _unique(cls, options: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(options)) != len(options):
            raise ValueError("the options of a question are unique")
        return options


class Evidence(BaseModel):
    """Read-only text shown with a choice: a property `name`, its `label` and the `text`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: Label
    text: str


def data_schema(fields: _Schema) -> dict[str, JsonValue]:
    """The schema of a `ctx.ask` request: the JSON Schema of its fields with the marker `data` (set last)."""
    return {**fields, MARKER: "data"}


def choice_schema(questions: Sequence[Question], evidence: Sequence[Evidence] = ()) -> dict[str, JsonValue]:
    """The schema of a choice request: one string property per question, then the read-only evidence properties.

    The evidence text is the property's `default` and its `maxLength` the text's length: the bound that spec 0006 leaves
    to a software setting has no value yet, so none is invented.

    Raises:
        ValueError: two properties share a name.
    """
    names = [*(q.name for q in questions), *(e.name for e in evidence)]
    if dupes := sorted({name for name in names if names.count(name) > 1}):
        raise ValueError(f"property names are not unique: {', '.join(dupes)}")
    props: dict[str, JsonValue] = {}
    for q in questions:
        props[q.name] = {"type": "string", "enum": list(q.options), "title": q.prompt}
    for e in evidence:
        props[e.name] = {**_EVIDENCE, "title": e.label, "maxLength": len(e.text), "default": e.text}
    return {"type": "object", MARKER: "choice", "properties": props}


def _questions(schema: _Schema) -> dict[str, list[JsonValue]]:
    """The questions of a choice schema, by name: its properties that have an `enum`."""
    props = schema.get("properties")
    if not isinstance(props, dict):
        return {}
    return {n: opts for n, p in props.items() if isinstance(p, dict) and isinstance(opts := p.get("enum"), list)}


def build_request(
    ids: IdSource, request_id: str, kind: Kind, title: str, schema: _Schema, evidence: Sequence[RefString] = ()
) -> InputRequest:
    """The request for `schema`, refused unless it carries the marker of its kind, so it is never presented unmarked.

    Raises:
        ContractError: `INTERNAL` (incident id from `ids`) when the marker is not `data` for kind `block` and `choice`
            for each `engine.*` kind, or a choice schema has no question.
    """
    want = "data" if kind == "block" else "choice"
    if schema.get(MARKER) != want or (want == "choice" and not _questions(schema)):
        shape = f"{MARKER} {want!r}" + (" and a question" if want == "choice" else "")
        message = f"request {request_id} ({kind}) was built without {shape}"
        raise ContractError(ErrorCode.INTERNAL, message, incident_id=ids.new_ulid())
    return InputRequest(request_id=request_id, kind=kind, title=title, fields_schema=schema, evidence=tuple(evidence))


def check_answer(request: InputRequest, answer: InputAnswer) -> None:
    """Accept `answer` if it fits `request`, else raise; a refusal changes nothing, so the request stays open.

    The answer quotes the request and the schema shown. A data request takes `values`; a choice request (a schema
    without the marker is one, fail-safe) takes `choices`: one option for each question and no other name.

    Raises:
        ContractError: `INVALID_ARGUMENT` for an answer that does not fit.
    """
    data = request.fields_schema.get(MARKER) == "data"
    questions = {} if data else _questions(request.fields_schema)
    given, why = answer.choices or {}, None
    if (answer.request_id, answer.shown_sha256) != (request.request_id, request.fields_schema_sha256):
        why = "it quotes another request or another schema than the one shown"
    elif (answer.values is not None) is not data:
        why = "a data request takes values and a choice request takes choices"
    elif not data and (given.keys() != questions.keys() or any(v not in questions[q] for q, v in given.items())):
        why = f"answer each of {sorted(questions)} with one of its options"
    if why is not None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, f"the answer to {request.request_id} is refused: {why}")


def escalation_request(ids: IdSource, run_id: str, escalated: ev.RunEscalated) -> InputRequest:
    """The `engine.escalation` request for a stop: why the run stopped, its evidence and how it may go on.

    The id is the same for the same run and cause, so a resume that stops again asks the same request. The one way on
    is `abandon` (`run_failed`, spec 0001 4.5.4); nothing presents the request yet.
    """
    why = Evidence(name="why", label="Why the run stopped", text=escalated.detail)
    ask = Question(name="next", prompt="How should the run go on", options=("abandon",))
    title, schema = f"The run stopped ({escalated.reason})", choice_schema([ask], [why])
    request_id = "esc_" + payload_sha256([run_id, escalated.reason, escalated.detail])[:32]
    return build_request(ids, request_id, "engine.escalation", title, schema, escalated.evidence)
