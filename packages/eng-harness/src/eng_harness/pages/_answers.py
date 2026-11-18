"""Answer models and the checks of a posted answer (spec 0006 4.4.5; AC29, AC31, AC32, AC39).

Purpose: the form of an approval or a choice becomes a validated submission and then the engine's answer. A submission
holds decisions, option ids, item ids, reasons and the engineer's name, and nothing that carries an engineering value.
Units: none. Errors: `AnswerError` (`status` 409 when the form quotes another hash than the open request's, else 400);
the message never holds more than an item id, and the page shows it escaped.
"""

import unicodedata
from collections.abc import Mapping
from http import HTTPStatus
from typing import Literal

from pydantic import BaseModel, ConfigDict

from eng_harness.ports import ApprovalAnswer, ApprovalRequest, InputAnswer, InputRequest

REASON_MAX = 500  # characters of a reason after trimming (spec 0006 AC31)
NAME_MAX = 100  # characters of the engineer's name (spec 0006 AC39)
REJECT, REASON, CHOICE = (
    "reject_",
    "reason_",
    "choice_",
)  # field prefixes (token-safe, AC49): rejected item, reason, option
type Request = ApprovalRequest | InputRequest


class AnswerError(Exception):
    """A posted answer failed a check; nothing is recorded."""

    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


class _Submission(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    shown_sha256: str
    by: str


class ApprovalSubmission(_Submission):
    """The validated form of an approval answer."""

    decision: Literal["approve", "reject"]
    rejected_items: tuple[str, ...] = ()
    item_reasons: Mapping[str, str]
    reason: str | None = None
    acknowledged_unreleased: bool = False

    def answer(self) -> ApprovalAnswer:
        """The engine's answer."""
        return ApprovalAnswer.model_validate(self.model_dump())


class ChoiceSubmission(_Submission):
    """The validated form of a choice: property name to option id."""

    choices: Mapping[str, str]

    def answer(self) -> InputAnswer:
        """The engine's answer."""
        return InputAnswer.model_validate(self.model_dump())


def bound_sha256(request: Request) -> str:
    """The hash an answer quotes: `shown_sha256` of an approval, `fields_schema_sha256` of an input request."""
    return request.shown_sha256 if isinstance(request, ApprovalRequest) else request.fields_schema_sha256


def engineer_name(text: str) -> str:
    """The name trimmed, 1 to 100 characters without control characters; never read from the operating system."""
    name = text.strip()
    if not 1 <= len(name) <= NAME_MAX or any(unicodedata.category(char) == "Cc" for char in name):
        raise AnswerError(f"the name has 1 to {NAME_MAX} characters, none of them a control character")
    return name


def parse(request: Request, form: Mapping[str, str]) -> ApprovalSubmission | ChoiceSubmission:
    """Check a posted form against the open `request` and return the submission.

    Raises:
        AnswerError: another hash than the request's (409), an invalid name, decision or reason, an item that is
            not one of the request's, a rejected item without a reason, or an approval that rejects every item.
    """
    sha = bound_sha256(request)
    if form.get("shown_sha256") != sha:
        raise AnswerError("the page was shown for another version of this request", HTTPStatus.CONFLICT)
    base = {"request_id": request.request_id, "shown_sha256": sha, "by": engineer_name(form.get("by", ""))}
    if isinstance(request, ApprovalRequest):
        return _approval(request, form, base)
    if not (choices := {k.removeprefix(CHOICE): v for k, v in form.items() if k.startswith(CHOICE)}):
        raise AnswerError("choose an option")
    return ChoiceSubmission.model_validate({**base, "choices": choices})


def _item_of(key: str) -> str:
    """The item id of a `REJECT` or `REASON` field: the key without the one prefix it starts with."""
    return key.removeprefix(REJECT if key.startswith(REJECT) else REASON)


def _approval(request: ApprovalRequest, form: Mapping[str, str], base: Mapping[str, str]) -> ApprovalSubmission:
    if (decision := form.get("decision")) not in ("approve", "reject"):
        raise AnswerError("choose approve or reject")
    items = set(request.items)
    if any(_item_of(k) not in items for k in form if k.startswith((REJECT, REASON))):
        raise AnswerError("the form names an item that is not an item of this request")
    rejected = tuple(i for i in request.items if REJECT + i in form)
    reasons = {i: text for i in request.items if (text := form.get(REASON + i, "").strip())}
    reason = form.get("reason", "").strip() or None
    if any(len(text) > REASON_MAX for text in (reason or "", *reasons.values())):
        raise AnswerError(f"a reason has at most {REASON_MAX} characters")
    if decision == "reject" and reason is None:
        raise AnswerError(f"a rejection needs a reason of 1 to {REASON_MAX} characters")
    if missing := [i for i in rejected if i not in reasons]:
        raise AnswerError(f"item {missing[0]} is rejected without a reason of its own")
    if decision == "approve" and items and items == set(rejected):
        raise AnswerError("every item is rejected: use reject")
    return ApprovalSubmission.model_validate(
        {
            **base, "decision": decision, "rejected_items": rejected, "item_reasons": reasons, "reason": reason,
            "acknowledged_unreleased": "acknowledged_unreleased" in form,
        }
    )  # fmt: skip
