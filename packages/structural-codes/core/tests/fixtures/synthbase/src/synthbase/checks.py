"""Checks of the synthetic pack: labels for the framework machinery, not engineering rules."""

from eng_contract.cited import Cited
from eng_contract.verdicts import SubjectKind

from structural_codes.applicability import Outcome, Precondition
from structural_codes.check import Check, check
from structural_codes.inputs import CheckInputs, bounded
from structural_codes.meta import CheckMeta
from structural_codes.trace import TraceRecorder

_LOW = Cited(value=0, unit="mm", source="synthetic lower bound")
_HIGH = Cited(value=100, unit="mm", source="synthetic upper bound")


class SynthInputs(CheckInputs):
    """Inputs of the synthetic checks."""

    width_mm: float = bounded(ge=_LOW, le=_HIGH, unit="mm")


def _meta(short_name: str, clause: str, unconditional: str | None) -> CheckMeta:
    return CheckMeta(
        check_id=f"synthbase.{clause.replace('.', '_')}.{short_name}",
        pack="synthbase",
        code="Synthetic Code",
        edition="1",
        clauses=(clause,),
        title=f"Synthetic check {short_name}",
        members=frozenset({SubjectKind.SECTION}),
        spec=f"synthbase/{short_name}.md",
        unconditional=unconditional,
    )


def _wide(inp: SynthInputs, t: TraceRecorder) -> bool:
    return t.const("limit_mm", _HIGH) > inp.width_mm


@check(meta=_meta("plain", "1.1", "synthetic clause spec section 1"), inputs=SynthInputs, preconditions=())
def plain(inp: SynthInputs, t: TraceRecorder) -> None:
    """Unconditional synthetic check."""


@check(
    meta=_meta("guarded", "2.1", None),
    inputs=SynthInputs,
    preconditions=(Precondition("P1", Outcome.NOT_APPLICABLE, "2.1", "synthetic width limit", _wide),),
)
def guarded(inp: SynthInputs, t: TraceRecorder) -> None:
    """Synthetic check with one declared precondition."""


SYNTH_CHECKS: tuple[Check, ...] = (guarded, plain)
