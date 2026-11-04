"""The check of the hash fixture pack: it imports one helper, which imports further helpers."""

from eng_contract.cited import Cited
from eng_contract.verdicts import SubjectKind

from structural_codes.check import Check, check
from structural_codes.inputs import CheckInputs, bounded
from structural_codes.meta import CheckMeta
from structural_codes.trace import TraceRecorder

from . import helpers

_LOW = Cited(value=0, unit="mm", source="synthetic lower bound")
_HIGH = Cited(value=100, unit="mm", source="synthetic upper bound")


class HashInputs(CheckInputs):
    """Inputs of the hash fixture check."""

    width_mm: float = bounded(ge=_LOW, le=_HIGH, unit="mm")


@check(
    meta=CheckMeta(
        check_id="hashpack.1_1.demo",
        pack="hashpack",
        code="Synthetic Code",
        edition="1",
        clauses=("1.1",),
        title="Synthetic hash check",
        members=frozenset({SubjectKind.SECTION, SubjectKind.MEMBER}),
        spec="hashpack/demo.md",
        unconditional="synthetic clause spec section 1",
    ),
    inputs=HashInputs,
    preconditions=(),
)
def demo(inp: HashInputs, t: TraceRecorder) -> None:
    """Call the helper so that the closure reaches it."""
    helpers.double(inp.width_mm)


DEMO: Check = demo
