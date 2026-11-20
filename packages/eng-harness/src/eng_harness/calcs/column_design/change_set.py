"""Calc `harness.column_change_set` v1: build a generated change set from matches (spec 0013 4.4.4).

Purpose: given the section-match results keyed by frame id and the frame ids whose decision is `change_section`, emit
one `frame_section` item (`frames: [id]`, `section`) per accepted frame with status `matched`, sorted by frame id;
every other accepted frame is an issue `NOT_IMPLEMENTED` with gap CW-G3 and no item. The set holds names only.
Units: none. Errors: `ContractError` `INVALID_ARGUMENT` for a duplicate `frame_id` in `matches`.
"""

from typing import Literal, Self

from eng_contract.errors import ContractError, ErrorCode
from pydantic import BaseModel, ConfigDict, model_validator

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.kinds.edit_cycle import Label

__all__ = ["ChangeSetBody", "ChangeSetInput", "MatchEntry", "column_change_set"]

_Status = Literal["matched", "no_section_in_model", "ambiguous"]
_SOURCE = "harness.column_change_set"


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class MatchEntry(_M):
    """One column's `harness.column_match/1` body with the frame id it belongs to (spec 0013 4.4.4)."""

    frame_id: Label
    status: _Status
    section: Label | None = None
    names: list[Label]

    @model_validator(mode="after")
    def _status_agrees(self) -> Self:
        one = self.section is not None and self.names == [self.section]
        none = self.section is None and not self.names
        several = self.section is None and len(self.names) > 1
        agreed = {"matched": one, "no_section_in_model": none, "ambiguous": several}[self.status]
        if not agreed:
            raise ValueError("section and names must agree with status")
        return self


class _FrameItem(_M):
    id: Label
    kind: Literal["frame_section"]
    frames: list[Label]
    section: Label


class _ChangeIssue(_M):
    frame_id: Label
    code: Literal["NOT_IMPLEMENTED"]
    gap: Literal["CW-G3"]


class ChangeSetInput(CalcInput):
    """The match results (with frame ids) and the accepted frame ids whose decision is `change_section`."""

    matches: list[MatchEntry]
    accepted: list[Label]


class ChangeSetBody(_M):
    """The payload of `harness.generated_change_set/1` without `calc`, `draft` and `trace`."""

    source: Label
    items: list[_FrameItem]
    issues: list[_ChangeIssue]
    note: Label | None = None
    benchmark_request: Label | None = None


@calc(
    id="harness.column_change_set",
    version=1,
    output_kind="harness.generated_change_set/1",
    title="Generated frame_section change set from matched column proposals",
    method_source="eng-harness spec 0013 §4.4.4; gap CW-G3",
    verification="draft",
)
def column_change_set(inp: ChangeSetInput, meta: InputMeta, trace: TraceBuilder) -> ChangeSetBody:
    """One frame_section item per accepted matched frame; CW-G3 issues for the rest.

    Raises:
        ContractError: a duplicate frame_id in matches.
    """
    _ = meta  # matches and accepted are resolved proposal answers, not record references
    by_frame: dict[str, MatchEntry] = {}
    for entry in inp.matches:
        if entry.frame_id in by_frame:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"duplicate match for frame {entry.frame_id}",
                field="matches",
            )
        by_frame[entry.frame_id] = entry
    accepted = sorted(set(inp.accepted))
    items: list[_FrameItem] = []
    issues: list[_ChangeIssue] = []
    for frame_id in accepted:
        match = by_frame.get(frame_id)
        if match is not None and match.status == "matched" and match.section is not None:
            items.append(_FrameItem(id=frame_id, kind="frame_section", frames=[frame_id], section=match.section))
        else:
            issues.append(_ChangeIssue(frame_id=frame_id, code="NOT_IMPLEMENTED", gap="CW-G3"))
    trace.input("matches", len(inp.matches))
    trace.input("accepted", len(accepted))
    trace.step("source", _SOURCE, formula="fixed label of this calc", source="spec 0013 4.4.4")
    trace.step(
        "items",
        len(items),
        formula="one frame_section per accepted frame with status matched, sorted by frame id",
        source="spec 0013 4.4.4",
        uses=["matches", "accepted"],
    )
    trace.step(
        "issues",
        len(issues),
        formula="accepted frames without a matched section: NOT_IMPLEMENTED CW-G3",
        source="spec 0013 4.4.4 CW-G3",
        uses=["matches", "accepted"],
    )
    trace.output("source", "items", "issues")
    return ChangeSetBody(source=_SOURCE, items=items, issues=issues)
