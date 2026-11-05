"""Input requests: the `x-eng-input` marker, choice schemas, answer checks and the escalation request (plan 0001 T11).

Covers spec 0001 4.9.1 and AC67: the marker of every request the engine builds (`data` for `ctx.ask`, `choice` for each
`engine.*` kind), the refusal of a schema built without a fitting marker, the hash that covers the marker, and the
refusal of an answer that does not fit its request. The requests of `engine.in_flight` and `engine.host_state` are
built here with the choices of spec 0001 4.5.3 and 4.5.4, as the tasks that present them will build them. Pure
functions over the in-memory fakes: no host, no clock, no randomness.
"""

import asyncio
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest
from eng_contract.canonical import payload_sha256
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_harness.engine._inputs import (
    MARKER,
    Evidence,
    Kind,
    Question,
    build_request,
    check_answer,
    choice_schema,
    data_schema,
)
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, JsonValue, ValidationError
from workflows.ctx_flows import flow
from workflows.rig import make_rig, request

from eng_harness.engine import RunStatus
from eng_harness.engine._runner import escalation_request
from eng_harness.journal import _events as ev
from eng_harness.ports import InputAnswer, InputRequest

IN_FLIGHT = Question(name="outcome", prompt="What happened to the write", options=("applied", "not_applied", "abandon"))
HOST_STATE = Question(name="state", prompt="What to do with the model", options=("accept", "restore", "abandon"))
DECISION = Question(name="pick", prompt="Which section", options=("w200", "w250"))
CHOICES: dict[Kind, Question] = {
    "engine.in_flight": IN_FLIGHT,
    "engine.host_state": HOST_STATE,
    "engine.decision": DECISION,
}
EVIDENCE = Evidence(name="why", label="Why the run stopped", text="the section is not covered")


class Fields(BaseModel):
    """Fields of a `ctx.ask` data request."""

    span: float
    note: str


def make_ids() -> SeededIdSource:
    """A fresh seeded id source (the incident ids of refusals)."""
    return SeededIdSource(b"harness", FixedClock(1_767_225_600_000, 1))


def data_request(ids: SeededIdSource) -> InputRequest:
    """A `ctx.ask` request over `Fields`."""
    return build_request(ids, "ask1", "block", "Section data", data_schema(Fields.model_json_schema()))


def choice_request(
    ids: SeededIdSource, question: Question = HOST_STATE, kind: Kind = "engine.host_state"
) -> InputRequest:
    """A choice request with one question and one evidence property."""
    return build_request(ids, f"id_{kind}", kind, "The model changed", choice_schema([question], [EVIDENCE]))


def answer(
    shown: InputRequest,
    *,
    values: Mapping[str, JsonValue] | None = None,
    choices: Mapping[str, str] | None = None,
    request_id: str | None = None,
    sha: str | None = None,
) -> InputAnswer:
    """An answer to `shown` (the id or the schema hash replaced when given)."""
    return InputAnswer(
        request_id=request_id or shown.request_id, shown_sha256=sha or shown.fields_schema_sha256,
        values=values, choices=choices, by="engineer:ann",
    )  # fmt: skip


def properties(shown: InputRequest) -> dict[str, dict[str, Any]]:
    """The properties of the request's schema."""
    return cast(dict[str, dict[str, Any]], shown.fields_schema["properties"])


def refused(shown: InputRequest, bad: InputAnswer) -> ContractError:
    """The refusal of `bad` (an `INVALID_ARGUMENT` error), after which `shown` still accepts a fitting answer."""
    with pytest.raises(ContractError) as error:
        check_answer(shown, bad)
    assert error.value.detail.code is ErrorCode.INVALID_ARGUMENT
    return error.value


def test_input_request_markers() -> None:
    ids = make_ids()
    asked = data_request(ids)
    assert asked.fields_schema[MARKER] == "data"  # ctx.ask: the JSON Schema of its fields plus the marker
    assert {k: v for k, v in asked.fields_schema.items() if k != MARKER} == Fields.model_json_schema()
    for kind, question in CHOICES.items():  # every engine.* kind built through the shared builder
        built = choice_request(ids, question, kind)
        assert (built.kind, built.fields_schema[MARKER]) == (kind, "choice")
    forged = data_schema({**Fields.model_json_schema(), MARKER: "choice"})  # a field model cannot set its own marker
    assert forged[MARKER] == "data"
    # the hash covers the marker: the same schema under another marker is another schema
    built = choice_request(ids)
    assert built.fields_schema_sha256 == payload_sha256(dict(built.fields_schema))
    assert built.fields_schema_sha256 != payload_sha256({**built.fields_schema, MARKER: "data"})
    assert asked.fields_schema_sha256 != payload_sha256({**asked.fields_schema, MARKER: "choice"})


def _enum_but_no_marker() -> dict[str, JsonValue]:
    return {k: v for k, v in choice_schema([HOST_STATE]).items() if k != MARKER}


@pytest.mark.parametrize(
    ("kind", "schema"),
    [
        ("block", {"type": "object"}),
        ("block", {"type": "object", MARKER: "choice"}),
        ("block", {"type": "object", MARKER: "other"}),
        ("engine.escalation", _enum_but_no_marker()),  # enum properties do not make a choice without the marker
        ("engine.in_flight", data_schema(Fields.model_json_schema())),
        ("engine.host_state", {**_enum_but_no_marker(), MARKER: "Choice"}),
        ("engine.decision", {"type": "object", MARKER: "choice", "properties": {"x": {"type": "string"}}}),
    ],
)
def test_schema_without_a_fitting_marker_is_refused(kind: Kind, schema: dict[str, JsonValue]) -> None:
    with pytest.raises(ContractError) as error:
        build_request(make_ids(), "r1", kind, "Title", schema)
    assert error.value.detail.code is ErrorCode.INTERNAL  # the engine's own bug: never presented
    assert error.value.detail.incident_id is not None


def test_choice_schema_follows_the_convention() -> None:
    schema = choice_schema([IN_FLIGHT, DECISION], [EVIDENCE])
    assert schema[MARKER] == "choice"
    props = cast(dict[str, dict[str, Any]], schema["properties"])
    assert set(props) == {"outcome", "pick", "why"}
    for question in (IN_FLIGHT, DECISION):  # one property per question: a string, its options, its prompt
        prop = props[question.name]
        assert (prop["type"], prop["enum"], prop["title"]) == ("string", list(question.options), question.prompt)
        assert "x-eng-evidence" not in prop
    why = props["why"]  # labeled, read-only, bounded evidence that holds its text
    assert (why["type"], why["title"], why["readOnly"], why["x-eng-evidence"]) == ("string", EVIDENCE.label, True, True)
    assert why["default"] == EVIDENCE.text
    assert isinstance(why["maxLength"], int)
    assert len(EVIDENCE.text) <= why["maxLength"]
    assert "enum" not in why  # evidence is not a question


@pytest.mark.parametrize("prompt", ["", "x" * 81, "a/b", "a\\b", "a:b", "me@home", "two\nlines"])
def test_prompt_and_options_are_checked(prompt: str) -> None:
    with pytest.raises(ValidationError):  # the prompt is a Label (spec 0005 4.2)
        Question(name="q", prompt=prompt, options=("a",))
    with pytest.raises(ValidationError):
        Evidence(name="e", label=prompt, text="t")
    with pytest.raises(ValidationError):
        Question(name="q", prompt="Fine", options=())
    with pytest.raises(ValidationError):
        Question(name="q", prompt="Fine", options=("a", "a"))


def test_property_names_are_unique() -> None:
    with pytest.raises(ValueError, match="why"):
        choice_schema([HOST_STATE], [EVIDENCE, EVIDENCE])
    with pytest.raises(ValueError, match="state"):
        choice_schema([HOST_STATE, HOST_STATE])


def test_answer_has_the_shape_of_its_request() -> None:
    ids = make_ids()
    asked, chosen = data_request(ids), choice_request(ids)
    check_answer(asked, answer(asked, values={"span": 6.0, "note": "n"}))  # a fitting answer is accepted
    check_answer(chosen, answer(chosen, choices={"state": "accept"}))
    refused(asked, answer(asked, choices={"state": "accept"}))  # choices to a data request
    refused(chosen, answer(chosen, values={"state": "accept"}))  # values to a choice request
    check_answer(asked, answer(asked, values={"span": 1.0}))  # the request stays open: a later fitting answer is taken
    check_answer(chosen, answer(chosen, choices={"state": "abandon"}))


@pytest.mark.parametrize(
    "bad",
    [{}, {"state": "later"}, {"state": "Accept"}, {"state": "accept", "extra": "accept"}, {"why": "accept"}],
)
def test_choice_answer_names_each_question_with_an_option(bad: dict[str, str]) -> None:
    chosen = choice_request(make_ids())
    refused(
        chosen, answer(chosen, choices=bad)
    )  # a question missing, a value outside its enum, a name that is no question
    check_answer(chosen, answer(chosen, choices={"state": "restore"}))


def test_answer_quotes_the_request_and_the_schema_shown() -> None:
    ids = make_ids()
    chosen, other = choice_request(ids), choice_request(ids, IN_FLIGHT, "engine.in_flight")
    refused(chosen, answer(chosen, choices={"state": "accept"}, sha=other.fields_schema_sha256))
    refused(chosen, answer(chosen, choices={"state": "accept"}, request_id=other.request_id))


def test_a_schema_without_the_marker_is_read_as_a_choice() -> None:
    unmarked = InputRequest(
        request_id="old1", kind="engine.host_state", title="Title", fields_schema=_enum_but_no_marker()
    )
    refused(unmarked, answer(unmarked, values={"state": "accept"}))  # fail-safe: nothing is answered as data
    check_answer(unmarked, answer(unmarked, choices={"state": "accept"}))


_OPTION = st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True)


@settings(derandomize=True, max_examples=100)
@given(options=st.lists(_OPTION, min_size=1, max_size=5, unique=True), value=_OPTION)
def test_only_an_option_of_the_question_is_accepted(options: list[str], value: str) -> None:
    chosen = build_request(
        make_ids(),
        "r1",
        "engine.decision",
        "Title",
        choice_schema([Question(name="q", prompt="Pick", options=tuple(options))]),
    )
    bad = answer(chosen, choices={"q": value})
    if value in options:
        check_answer(chosen, bad)
    else:
        refused(chosen, bad)


def test_escalation_request(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)

    async def body(ctx: Any) -> list[str]:
        first = await ctx.tool("read_a", {"n": 0})
        await ctx.escalate("the section is not covered", [first.ref])
        raise AssertionError("escalate does not return")

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.status is RunStatus.NEEDS_ENGINEER
    stopped = outcome.escalation
    assert isinstance(stopped, ev.RunEscalated)
    journal = rig.types(outcome.run_id)
    shown = escalation_request(rig.ids, outcome.run_id, stopped)
    assert (shown.kind, shown.fields_schema[MARKER]) == ("engine.escalation", "choice")
    assert shown.evidence == tuple(stopped.evidence)  # the evidence references of the stop
    assert len(shown.evidence) == 1
    assert stopped.reason in shown.title
    texts = [p["default"] for p in properties(shown).values() if p.get("x-eng-evidence")]
    assert texts == [stopped.detail]  # the reason the run stopped is shown as read-only evidence
    assert re.fullmatch(r"esc_[0-9a-f]{32}", shown.request_id)
    # a resume that escalates again for the same cause asks the same request; another run asks another
    again = escalation_request(rig.ids, outcome.run_id, stopped)
    assert (again.request_id, again.fields_schema_sha256) == (shown.request_id, shown.fields_schema_sha256)
    assert escalation_request(rig.ids, "run_other", stopped).request_id != shown.request_id
    # the only way on that spec 0001 defines for a stopped run is to abandon it (run_failed, reason abandoned)
    options = [p["enum"] for p in properties(shown).values() if "enum" in p]
    assert options == [["abandon"]]
    name = next(n for n, p in properties(shown).items() if "enum" in p)
    check_answer(shown, answer(shown, choices={name: "abandon"}))
    refused(shown, answer(shown, choices={name: "retry"}))
    # building the request presents nothing and journals nothing: the journal of an escalation is run_escalated alone
    assert rig.inputs.presented == []
    assert rig.types(outcome.run_id) == journal
