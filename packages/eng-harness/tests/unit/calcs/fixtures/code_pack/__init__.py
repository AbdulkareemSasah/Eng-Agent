"""Synthetic code pack `calcs` for the code-pack route tests (plan 0010 T2): structural fixtures only.

Every constant cites "synthetic test fixture, no engineering meaning"; the numbers label the machinery, not a project.
The pack is named `calcs` because the check content hash follows the imports of the pack's top-level package, and
this module is `calcs.fixtures.code_pack` (the test folder `tests/unit/calcs`).
"""

from eng_contract.cited import Cited
from eng_contract.verdicts import SubjectKind
from structural_codes.check import Check, check
from structural_codes.errors import NotImplementedGap
from structural_codes.inputs import CheckInputs, bounded
from structural_codes.meta import CheckMeta, GapDecl
from structural_codes.pack import Pack
from structural_codes.trace import TraceRecorder

_SRC = "synthetic test fixture, no engineering meaning"
_LOW = Cited(value=0, unit="mm", source=_SRC)
_HIGH = Cited(value=1000, unit="mm", source=_SRC)
SOURCE_KIND = "harness.run_output/1"
SIZED_ID = "calcs.3_1.sized"
GAP_ID = "calcs.6_1.gap"
SILENT_ID = "calcs.7_1.silent"
OTHER_ID = "calcs.8_1.other"
VERSION = "0.0.1"
SIZED_VERSION = 3


class SizedInputs(CheckInputs):
    """`demand_mm` must be a reference (an engineering quantity); `capacity_mm` may be a literal."""

    demand_mm: float = bounded(
        ge=_LOW, le=_HIGH, unit="mm", ref_capable=True, ref_kinds=frozenset({SOURCE_KIND}), engineering_quantity=True
    )
    capacity_mm: float = bounded(ge=_LOW, le=_HIGH, unit="mm", ref_capable=True)


def _meta(check_id: str, clause: str, short: str, gaps: tuple[GapDecl, ...] = (), version: int = 1) -> CheckMeta:
    return CheckMeta(
        check_id=check_id,
        pack="calcs",
        code="Synthetic Code",
        edition="1",
        clauses=(clause,),
        title=f"Synthetic route check {short}",
        members=frozenset({SubjectKind.FOOTING}),
        spec=f"calcs/{short}.md",
        unconditional="synthetic clause spec section 1",
        gaps=gaps,
        version=version,
    )


@check(meta=_meta(SIZED_ID, "3.1", "sized", version=SIZED_VERSION), inputs=SizedInputs, preconditions=())
def sized(inp: SizedInputs, t: TraceRecorder) -> None:
    """One verdict from the demand and capacity inputs."""
    t.verdict(demand="demand_mm", capacity="capacity_mm")


@check(
    meta=_meta(GAP_ID, "6.1", "gap", gaps=(GapDecl(id="G-3", clause="6.1", reason="synthetic declared gap"),)),
    inputs=SizedInputs,
    preconditions=(),
)
def gap(inp: SizedInputs, t: TraceRecorder) -> None:
    """Raises a declared gap: the verdict is `NEEDS_ENGINEER`, not an error."""
    raise NotImplementedGap("G-3", clause="6.1", reason="synthetic gap reason")


@check(meta=_meta(SILENT_ID, "7.1", "silent"), inputs=SizedInputs, preconditions=())
def silent(inp: SizedInputs, t: TraceRecorder) -> None:
    """Records no verdict: a definition defect that the pack raises as `CheckDefinitionError`."""


@check(meta=_meta(OTHER_ID, "8.1", "other"), inputs=SizedInputs, preconditions=())
def other(inp: SizedInputs, t: TraceRecorder) -> None:
    """A registered check that the tests keep out of the route's allowlist."""
    t.verdict(demand="demand_mm", capacity="capacity_mm")


CHECKS: tuple[Check, ...] = (gap, other, silent, sized)

PACK = Pack(
    name="calcs", code="Synthetic Code", edition="1", version=VERSION, checks=CHECKS, approvals="approvals.yaml"
)
