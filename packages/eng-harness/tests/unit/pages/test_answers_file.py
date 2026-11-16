"""`pages.accept_answers_file`: the only way a file becomes an `InputAnswer` (plan 0006 T10; spec 0006 AC46)."""

import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from pydantic import JsonValue

from eng_harness.engine._inputs import Question, build_request, choice_schema, data_schema
from eng_harness.pages import accept_answers_file
from eng_harness.ports import InputRequest

IDS = SeededIdSource(b"file", FixedClock(1_767_225_600_000, 1))
FIELDS: dict[str, JsonValue] = {"type": "object", "properties": {"x": {"type": "number"}}}


def _choice(rid: str, kind: str) -> InputRequest:
    ask = Question(name="next", prompt="Next", options=("accept", "more_edits", "hand_edit"))
    schema = choice_schema([ask])
    return InputRequest.model_validate({"request_id": rid, "kind": kind, "title": "t", "fields_schema": schema})


def test_file_accepts_a_data_request_for_the_named_engineer() -> None:
    request = build_request(IDS, "inp_data", "block", "t", data_schema(FIELDS), ())
    answer = accept_answers_file(request, {"x": 1.5}, "Ada")
    assert answer.request_id == "inp_data"
    assert answer.shown_sha256 == request.fields_schema_sha256
    assert dict(answer.values or {}) == {"x": 1.5}
    assert answer.choices is None
    assert answer.by == "Ada"
    for bad in ("", "  ", "a\nb"):
        with pytest.raises(ContractError, match=r"\[engine\] engineer") as refused:
            accept_answers_file(request, {"x": 1}, bad)
        assert refused.value.detail.code == ErrorCode.INVALID_ARGUMENT


def test_file_refuses_choice_engine_and_unmarked_requests() -> None:
    unmarked = InputRequest(request_id="inp_none", kind="block", title="t", fields_schema={"type": "object"})
    wrong_kind = InputRequest(
        request_id="inp_dec", kind="engine.decision", title="t", fields_schema=data_schema(FIELDS)
    )
    engine_id = InputRequest(request_id="engine.x", kind="block", title="t", fields_schema=data_schema(FIELDS))
    refused = [
        _choice("dec_turn", "engine.decision"),  # the engineer turn and batched decisions
        _choice("inp_block", "block"),  # a choice marker on a block request
        _choice("engine.in_flight", "engine.in_flight"),
        _choice("engine.host_state", "engine.host_state"),
        _choice("engine.escalation", "engine.escalation"),
        unmarked,
        wrong_kind,
        engine_id,
    ]
    for request in refused:
        with pytest.raises(ContractError) as error:
            accept_answers_file(request, {"next": "accept"}, "Ada")
        assert error.value.detail.code == ErrorCode.INVALID_ARGUMENT
        assert request.request_id in str(error.value)
