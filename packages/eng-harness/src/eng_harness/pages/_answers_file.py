"""The answers-file gate (spec 0006 4.2.1, AC2, AC46, AC64): the only way a file becomes an `InputAnswer`.

Purpose: a file is data, so it can answer a `ctx.ask` request (kind `block`, schema marker `x-eng-input: data`) and
nothing else; the engineer turn, batched decisions, `engine.*` requests and unmarked requests are choices and are
answered on the page only. Units: none. Errors: `ContractError` `INVALID_ARGUMENT` (exit 2), with nothing journaled.
"""

from collections.abc import Mapping

from eng_contract.errors import ContractError, ErrorCode
from pydantic import JsonValue

from eng_harness.engine._inputs import MARKER
from eng_harness.pages._answers import AnswerError, engineer_name
from eng_harness.ports import InputAnswer, InputRequest


def accept_answers_file(request: InputRequest, payload: Mapping[str, JsonValue], by: str) -> InputAnswer:
    """The answer `payload` (the file's object) gives to `request`, for the engineer `by` (the `[engine] engineer`).

    The engine validates the values against the request's model; this gate decides only whether a file may answer.

    Raises:
        ContractError: `INVALID_ARGUMENT` when `request` is not of kind `block`, its id starts with `engine.` or its
            schema does not carry `x-eng-input: data`, or when `by` is not a valid name.
    """
    if (
        request.kind != "block"
        or request.request_id.startswith("engine.")
        or request.fields_schema.get(MARKER) != "data"
    ):
        message = f"request {request.request_id} is not a data request: it is answered on the page, not by a file"
        raise ContractError(ErrorCode.INVALID_ARGUMENT, message)
    try:
        name = engineer_name(by)
    except AnswerError as bad:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, f"set [engine] engineer to a valid name: {bad}") from None
    return InputAnswer(
        request_id=request.request_id, shown_sha256=request.fields_schema_sha256, values=dict(payload), by=name
    )
