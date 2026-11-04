"""Verdict construction and governing selection (spec 0001 sections 4.5 and 3.3; 04-tool-contract section 5.1).

Purpose: decide the status of one demand/capacity pair, turn the recorder's drafts into contract `Verdict` values and
mark the governing verdict of each subject. R1 module: a mistake here is a wrong `PASS` or `FAIL`.
Units: demand and capacity are `Quantity` values in one unit of one dimension; ratio and ratio limit have none.
Errors: `CheckDefinitionError` for a clause that is not one of the check's `clauses`. An unusable demand or
capacity gives an `ERROR` verdict, never an exception (AC12).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from eng_contract.quantity import Quantity
from eng_contract.verdicts import Subject, SubjectKind, Verdict, VerdictSource, VerdictStatus

from structural_codes.errors import CheckDefinitionError
from structural_codes.meta import CheckMeta

__all__ = ["DEFAULT_RATIO_LIMIT", "VerdictDraft", "assess", "assign_governing", "build_verdict"]

DEFAULT_RATIO_LIMIT: float = float(Verdict.model_fields["ratio_limit"].default)
"""The contract default of `ratio_limit` (04-tool-contract section 5.1)."""

_SIZED = (VerdictStatus.PASS, VerdictStatus.FAIL)


@dataclass(frozen=True, slots=True)
class VerdictDraft:
    """A verdict as recorded by `TraceRecorder.verdict`, before the runner adds the check, subject and trace."""

    status: VerdictStatus
    demand_name: str
    capacity_name: str
    demand: Quantity
    capacity: Quantity
    ratio_name: str | None
    ratio: float | None
    ratio_limit: float
    clause: str | None
    assumptions: tuple[str, ...]


def assess(
    demand_name: str, demand: float, capacity_name: str, capacity: float, limit: float
) -> tuple[float | None, VerdictStatus, str | None]:
    """Return (ratio, status, message) for one pair of finite values in one unit.

    `PASS` iff `demand / capacity <= limit` in exact float64 (AC11). A capacity `<= 0`, a demand `< 0` or a ratio
    beyond float64 gives (None, `ERROR`, message naming the value) (AC12; spec 4.5 [added]).
    """
    if capacity <= 0:
        return None, VerdictStatus.ERROR, f"verdict ERROR: {capacity_name} = {capacity:g} is not above zero"
    if demand < 0:
        return None, VerdictStatus.ERROR, f"verdict ERROR: {demand_name} = {demand:g} is below zero"
    ratio = demand / capacity
    if not math.isfinite(ratio):
        return None, VerdictStatus.ERROR, f"verdict ERROR: {demand_name} / {capacity_name} is not finite"
    return ratio, (VerdictStatus.PASS if ratio <= limit else VerdictStatus.FAIL), None


def build_verdict(draft: VerdictDraft, meta: CheckMeta, subject: Subject, *, trace_index: int) -> Verdict:
    """Return the contract `Verdict` of a draft (AC15); `governing` is left false for `assign_governing`.

    The clause is the draft's, which must be one of `meta.clauses`, or else the first clause; the assumptions are the
    check's followed by the draft's. `trace_ref` is the local `#/traces/<trace_index>`.

    Raises:
        CheckDefinitionError: the draft's clause is not one of `meta.clauses`.
    """
    clause = meta.clauses[0] if draft.clause is None else draft.clause
    if clause not in meta.clauses:
        raise CheckDefinitionError(f"{meta.check_id}: clause {clause!r} is not one of {list(meta.clauses)}")
    return Verdict(
        source=VerdictSource.CODE_PACK,
        check_id=meta.check_id,
        code=meta.code,
        clause=clause,
        subject=subject,
        demand=draft.demand,
        capacity=draft.capacity,
        ratio=draft.ratio,
        ratio_limit=draft.ratio_limit,
        status=draft.status,
        trace_ref=f"#/traces/{trace_index}",
        assumptions=[*meta.assumptions, *draft.assumptions],
    )


def assign_governing(verdicts: Sequence[Verdict]) -> list[Verdict]:
    """Return copies of `verdicts` in order with `governing` set by the rule of AC14.

    For each subject (its kind and id: the cases and stations of one member compete) exactly the `PASS` or `FAIL`
    verdict with the largest ratio is governing, the first in order on a tie; a subject without one has none. Any
    `governing` value on the input is replaced, so a check body cannot set it.
    """
    best: dict[tuple[SubjectKind, str], tuple[int, float]] = {}
    for index, verdict in enumerate(verdicts):
        if verdict.status not in _SIZED or verdict.ratio is None:
            continue
        key = (verdict.subject.kind, verdict.subject.id)
        if key not in best or verdict.ratio > best[key][1]:
            best[key] = (index, verdict.ratio)
    chosen = {index for index, _ in best.values()}
    return [verdict.model_copy(update={"governing": index in chosen}) for index, verdict in enumerate(verdicts)]
