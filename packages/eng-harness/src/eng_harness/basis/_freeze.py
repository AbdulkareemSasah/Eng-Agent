"""Freeze: confirmation to a stored design basis (spec 0004 section 4.6, AC22 to AC24).

Purpose: `freeze` checks the engineer's answer against the draft, marks the fields of the confirmed sections as
confirmed, stamps values-file fields `engineer:<by>@<at>` from the answer, requires a complete basis and stores one
`basis.design_basis/1` result. Nothing is stored when any check fails. Confirmation is per run: it is read from the
answer only, never from earlier runs.
Errors: `BasisNotConfirmed` (reasons `draft_changed`, `section_incomplete`, `nothing_confirmed`, `rejected`),
`BasisIncomplete` (`paths`), `BasisInvalid` (`field_invalid`); all carry contract code INVALID_ARGUMENT.
"""

# ruff: noqa: N818  # B-162: names fixed by spec 0004 section 6

from typing import Annotated, Literal

from eng_contract.envelope import LiteralInput, Provenance
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import Clock
from eng_contract.kinds.basis import DesignBasis
from eng_contract.store import ResultStore
from pydantic import BaseModel, ConfigDict, JsonValue, StringConstraints, ValidationError

from eng_harness import __version__
from eng_harness.basis._build import BasisDraft
from eng_harness.basis._fields import BasisInvalid
from eng_harness.basis._setup import BasisSetupAnswer

NotConfirmedReason = Literal["draft_changed", "section_incomplete", "nothing_confirmed", "rejected"]
KIND = "basis.design_basis/1"


class BasisNotConfirmed(ContractError):
    """The answer does not confirm this draft; `reason` is the key."""

    def __init__(self, reason: NotConfirmedReason) -> None:
        """Build the error; the message holds only the reason key."""
        self.reason: NotConfirmedReason = reason
        super().__init__(ErrorCode.INVALID_ARGUMENT, f"basis not confirmed: {reason}")


class BasisIncomplete(ContractError):
    """A required field is missing or a present field is unconfirmed; `paths` lists them."""

    def __init__(self, paths: tuple[str, ...]) -> None:
        """Build the error; the message holds only the paths."""
        self.paths = paths
        super().__init__(ErrorCode.INVALID_ARGUMENT, f"basis incomplete: {', '.join(paths)}")


class FrozenBasis(BaseModel):
    """The stored basis: `ref` is the value for `RunRequest.basis_ref` (the result id)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    ref: str
    result_id: str
    payload_sha256: Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]


def _check_answer(draft: BasisDraft, answer: BasisSetupAnswer) -> tuple[str, str, frozenset[str]]:
    """Return `by`, `at` and the confirmed sections, or raise `BasisNotConfirmed` (AC22)."""
    if answer.rejected is not None:
        raise BasisNotConfirmed("rejected")
    if answer.draft_sha256 != draft.sha256:
        raise BasisNotConfirmed("draft_changed")
    sections = frozenset(answer.confirmed_sections or ())
    if not sections or answer.by is None or answer.at is None:
        raise BasisNotConfirmed("nothing_confirmed")
    if not sections <= {spec.path.partition(".")[0] for spec in draft.specs}:
        raise BasisNotConfirmed("draft_changed")
    if sections & {path.partition(".")[0] for path in draft.pending}:
        raise BasisNotConfirmed("section_incomplete")
    return answer.by, answer.at, sections


def freeze(draft: BasisDraft, answer: BasisSetupAnswer, store: ResultStore, clock: Clock) -> FrozenBasis:
    """Store the confirmed draft as one `basis.design_basis/1` result and return its reference (AC22 to AC24).

    Raises:
        BasisNotConfirmed: the answer rejects, is bound to another draft, confirms nothing, or confirms a section
            with a pending required field.
        BasisIncomplete: a required field is missing or any present field is in an unconfirmed section.
        BasisInvalid: `field_invalid`, the fields do not form a valid basis.
        ContractError: the store refused or failed the write.
    """
    by, at, sections = _check_answer(draft, answer)
    fields: dict[str, JsonValue] = {
        path: {
            "value": found.value,
            "unit": found.unit,
            "source": found.source or f"engineer:{by}@{at}",
            "confirmed": path.partition(".")[0] in sections,
            "citation": found.citation,
        }
        for path, found in draft.fields.items()
    }
    template = draft.template
    head: JsonValue = (
        None if template is None else {"name": template.name, "version": template.version, "sha256": template.sha256}
    )
    try:
        basis = DesignBasis.model_validate({"template": head, "fields": fields})
    except ValidationError as error:
        raise BasisInvalid("field_invalid") from error
    missing = basis.missing([spec.path for spec in draft.specs if spec.required])
    unconfirmed = [path for path, field in basis.fields.items() if not field.confirmed and path not in missing]
    if missing or unconfirmed:
        raise BasisIncomplete((*missing, *unconfirmed))
    producer = Provenance(
        tool="harness",
        tool_version=__version__,
        inputs={"draft_sha256": LiteralInput(literal=draft.sha256)},
        started_at=clock.now(),
        duration_ms=0,
    )
    record = store.put(KIND, basis.model_dump(mode="json"), producer)
    return FrozenBasis(ref=record.result_id, result_id=record.result_id, payload_sha256=record.payload_sha256)
