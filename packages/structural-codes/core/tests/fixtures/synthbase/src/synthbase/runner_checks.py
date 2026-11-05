"""Runner fixtures of the synthetic pack: checks for the evaluate tests, no engineering content.

Every constant cites "synthetic test fixture, no engineering meaning"; the numbers are labels for the machinery.
"""

import math
from typing import Literal

from eng_contract.cited import Cited
from eng_contract.verdicts import SubjectKind

from structural_codes.applicability import Outcome, Precondition
from structural_codes.check import Check, check
from structural_codes.errors import NotImplementedGap
from structural_codes.inputs import CheckInputs, bounded
from structural_codes.meta import CheckMeta, GapDecl
from structural_codes.pack import Pack
from structural_codes.trace import TraceRecorder

_SRC = "synthetic test fixture, no engineering meaning"
_ZERO = Cited(value=0, unit="mm", source=_SRC)
_HIGH = Cited(value=100, unit="mm", source=_SRC)
_FORCE_LOW = Cited(value=0, unit="mm", source=_SRC)
_FORCE_HIGH = Cited(value=1000, unit="mm", source=_SRC)
_LIMIT_1 = Cited(value=50, unit="mm", source=_SRC)
_LIMIT_2 = Cited(value=20, unit="mm", source=_SRC)
_KIND = "model.sections/1"


class SizedInputs(CheckInputs):
    """Inputs of the runner checks; `fault` selects an arithmetic failure inside the body."""

    width_mm: float = bounded(ge=_ZERO, le=_HIGH, unit="mm", ref_capable=True, ref_kinds=frozenset({_KIND}))
    demand_mm: float = bounded(ge=_FORCE_LOW, le=_FORCE_HIGH, unit="mm")
    capacity_mm: float = bounded(ge=_FORCE_LOW, le=_FORCE_HIGH, unit="mm")
    fault: Literal["none", "zero", "overflow", "domain", "nan", "value", "other"] = "none"


def _meta(
    short_name: str,
    clause: str,
    *,
    members: frozenset[SubjectKind] = frozenset({SubjectKind.SECTION}),
    unconditional: str | None = None,
    gaps: tuple[GapDecl, ...] = (),
) -> CheckMeta:
    return CheckMeta(
        check_id=f"synthbase.{clause.replace('.', '_')}.{short_name}",
        pack="synthbase",
        code="Synthetic Code",
        edition="1",
        clauses=(clause, "9.9"),
        title=f"Synthetic runner check {short_name}",
        members=members,
        spec=f"synthbase/{short_name}.md",
        unconditional=unconditional,
        gaps=gaps,
        assumptions=("synthetic assumption",),
    )


def _wider_than_first(inp: SizedInputs, t: TraceRecorder) -> bool:
    return t.const("limit_one_mm", _LIMIT_1) > inp.width_mm


def _wider_than_second(inp: SizedInputs, t: TraceRecorder) -> bool:
    return t.const("limit_two_mm", _LIMIT_2) > inp.width_mm


def _fail_by_fault(inp: SizedInputs, t: TraceRecorder) -> None:
    if inp.fault == "zero":
        t.step("bad", 1.0 / (inp.width_mm - inp.width_mm), unit="1", formula="1 / 0", source=_SRC, uses=["width_mm"])
    elif inp.fault == "overflow":
        t.step("bad", math.exp(1000.0 + inp.width_mm), unit="1", formula="exp", source=_SRC, uses=["width_mm"])
    elif inp.fault == "domain":
        t.step("bad", math.sqrt(-1.0 - inp.width_mm), unit="1", formula="sqrt", source=_SRC, uses=["width_mm"])
    elif inp.fault == "nan":
        t.step("bad", math.nan, unit="1", formula="nan", source=_SRC, uses=["width_mm"])
    elif inp.fault == "value":
        raise ValueError("synthetic non-math failure")
    elif inp.fault == "other":
        raise RuntimeError("synthetic unexpected failure")


@check(
    meta=_meta("sized", "3.1", unconditional="synthetic clause spec section 1"), inputs=SizedInputs, preconditions=()
)
def sized(inp: SizedInputs, t: TraceRecorder) -> None:
    """Records one verdict from the demand and capacity inputs, after the selected fault."""
    _fail_by_fault(inp, t)
    t.verdict(demand="demand_mm", capacity="capacity_mm")


@check(
    meta=_meta("two_pre", "4.1"),
    inputs=SizedInputs,
    preconditions=(
        Precondition("P1", Outcome.NOT_APPLICABLE, "4.1", "synthetic first limit", _wider_than_first),
        Precondition("P2", Outcome.NEEDS_ENGINEER, "4.2", "synthetic second limit", _wider_than_second),
    ),
)
def two_pre(inp: SizedInputs, t: TraceRecorder) -> None:
    """Two declared preconditions, then one verdict."""
    t.verdict(demand="demand_mm", capacity="capacity_mm")


@check(
    meta=_meta("scoped", "5.1", members=frozenset({SubjectKind.FOOTING})),
    inputs=SizedInputs,
    preconditions=(Precondition("P1", Outcome.NOT_APPLICABLE, "5.1", "synthetic limit", _wider_than_first),),
)
def scoped(inp: SizedInputs, t: TraceRecorder) -> None:
    """Footing-only check with a precondition."""
    t.verdict(demand="demand_mm", capacity="capacity_mm")


@check(
    meta=_meta(
        "scoped_free",
        "5.2",
        members=frozenset({SubjectKind.FOOTING}),
        unconditional="synthetic clause spec section 2",
    ),
    inputs=SizedInputs,
    preconditions=(),
)
def scoped_free(inp: SizedInputs, t: TraceRecorder) -> None:
    """Footing-only check without preconditions."""
    t.verdict(demand="demand_mm", capacity="capacity_mm")


@check(
    meta=_meta(
        "gap",
        "6.1",
        unconditional="synthetic clause spec section 3",
        gaps=(GapDecl(id="G-3", clause="6.1", reason="synthetic declared gap"),),
    ),
    inputs=SizedInputs,
    preconditions=(),
)
def gap(inp: SizedInputs, t: TraceRecorder) -> None:
    """Records a verdict, then raises a declared gap: the gap verdict replaces it."""
    t.verdict(demand="demand_mm", capacity="capacity_mm")
    raise NotImplementedGap("G-3", clause="6.1", reason="synthetic gap reason")


@check(
    meta=_meta("gap_undeclared", "6.2", unconditional="synthetic clause spec section 4"),
    inputs=SizedInputs,
    preconditions=(),
)
def gap_undeclared(inp: SizedInputs, t: TraceRecorder) -> None:
    """Raises a gap that the metadata does not declare."""
    raise NotImplementedGap("G-9", clause="6.2", reason="synthetic undeclared gap")


def _gap_in_precondition(inp: SizedInputs, t: TraceRecorder) -> bool:
    raise NotImplementedGap("G-4", clause="6.3", reason="synthetic precondition gap")


@check(
    meta=_meta("gap_pre", "6.3", gaps=(GapDecl(id="G-4", clause="6.3", reason="synthetic declared gap"),)),
    inputs=SizedInputs,
    preconditions=(Precondition("P1", Outcome.NOT_APPLICABLE, "6.3", "synthetic limit", _gap_in_precondition),),
)
def gap_pre(inp: SizedInputs, t: TraceRecorder) -> None:
    """Never reached: the precondition test raises a declared gap."""
    t.verdict(demand="demand_mm", capacity="capacity_mm")


@check(
    meta=_meta("silent", "7.1", unconditional="synthetic clause spec section 5"), inputs=SizedInputs, preconditions=()
)
def silent(inp: SizedInputs, t: TraceRecorder) -> None:
    """Records a step but no verdict."""
    t.step("half_mm", inp.width_mm / 2, unit="mm", formula="width_mm / 2", source=_SRC, uses=["width_mm"])


RUNNER_CHECKS: tuple[Check, ...] = (gap, gap_pre, gap_undeclared, scoped, scoped_free, silent, sized, two_pre)

RUNNER_PACK = Pack(
    name="synthbase",
    code="Synthetic Code",
    edition="1",
    version="0.0.2",
    checks=RUNNER_CHECKS,
    approvals="approvals.yaml",
)
