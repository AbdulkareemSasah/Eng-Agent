"""Own checks of the synthetic overlay pack (an overridden and an added check): labels, no engineering content.

Every constant cites "synthetic test fixture, no engineering meaning".
"""

from eng_contract.cited import Cited
from eng_contract.verdicts import SubjectKind

from structural_codes.check import Check, check
from structural_codes.inputs import CheckInputs, bounded
from structural_codes.meta import CheckMeta
from structural_codes.trace import TraceRecorder

_SRC = "synthetic test fixture, no engineering meaning"
_LOW = Cited(value=0, unit="mm", source=_SRC)
_HIGH = Cited(value=1000, unit="mm", source=_SRC)
CODE = "Synthetic Overlay Code"


class OverInputs(CheckInputs):
    """Inputs of the overlay's own checks."""

    demand_mm: float = bounded(ge=_LOW, le=_HIGH, unit="mm")
    capacity_mm: float = bounded(ge=_LOW, le=_HIGH, unit="mm")


def _meta(short_name: str, clause: str) -> CheckMeta:
    return CheckMeta(
        check_id=f"synthover.{clause.lower().replace('.', '_')}.{short_name}",
        pack="synthover",
        code=CODE,
        edition="2",
        clauses=(clause,),
        title=f"Synthetic overlay check {short_name}",
        members=frozenset({SubjectKind.SECTION}),
        spec=f"synthover/{short_name}.md",
        unconditional="synthetic clause spec section 1",
    )


@check(meta=_meta("sized_over", "S3.1"), inputs=OverInputs, preconditions=())
def sized_over(inp: OverInputs, t: TraceRecorder) -> None:
    """Overrides the base sized check: the capacity is doubled before the ratio."""
    t.step("double_mm", 2 * inp.capacity_mm, unit="mm", formula="2 * capacity_mm", source=_SRC, uses=["capacity_mm"])
    t.verdict(demand="demand_mm", capacity="double_mm")


@check(meta=_meta("extra", "A1.1"), inputs=OverInputs, preconditions=())
def extra(inp: OverInputs, t: TraceRecorder) -> None:
    """Added check with no base counterpart: ratio of the plain demand and capacity."""
    t.verdict(demand="demand_mm", capacity="capacity_mm")


OWN_CHECKS: tuple[Check, ...] = (extra, sized_over)
