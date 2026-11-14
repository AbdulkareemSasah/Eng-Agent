"""The answer models hold decisions, option ids and reasons, never an engineering value (plan 0006 T7; AC32)."""

import typing
from collections.abc import Iterator

import pytest
from pydantic import BaseModel, ValidationError

from eng_harness.pages._answers import ApprovalSubmission, ChoiceSubmission

ALLOWED = {
    "request_id", "shown_sha256", "decision", "choices", "rejected_items", "item_reasons", "reason", "by",
    "acknowledged_unreleased", "confirmed_sections",
}  # fmt: skip
SHA = "a" * 64
APPROVAL = {"request_id": "r", "shown_sha256": SHA, "by": "ada", "decision": "approve", "item_reasons": {}}
CHOICE = {"request_id": "r", "shown_sha256": SHA, "by": "ada", "choices": {"q": "a"}}


def _leaves(annotation: object) -> Iterator[object]:
    """The types a member is built from: a literal is a string, a tuple of strings has the leaf `str`."""
    if typing.get_origin(annotation) is typing.Literal:
        yield str
    elif args := typing.get_args(annotation):
        for arg in args:
            yield from _leaves(arg)
    else:
        yield annotation


@pytest.mark.parametrize("model", [ApprovalSubmission, ChoiceSubmission])
def test_answers_carry_no_values(model: type[BaseModel]) -> None:
    assert set(model.model_fields) <= ALLOWED
    for name, info in model.model_fields.items():
        assert set(_leaves(info.annotation)) <= {str, bool, type(None), Ellipsis}, name  # no number, no quantity
    body = APPROVAL if model is ApprovalSubmission else CHOICE
    assert model.model_validate(body)
    with pytest.raises(ValidationError):
        model.model_validate({**body, "value": 1.5})  # an extra member is refused
    with pytest.raises(ValidationError):
        model.model_validate({**body, "by": 7})  # no coercion of a number into a text member
