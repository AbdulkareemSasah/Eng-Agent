"""Check `aci318_14.13_3_1_1.bearing_pressure_service`: service soil pressure under an isolated footing. R1 module.

Purpose: the largest service soil pressure of a rigid rectangular footing (FS S1 to S5, linear pressure, full
contact) against the permissible gross pressure of the design basis (ACI 318-14 13.3.1.1; clause spec
`docs/clauses/aci318_14/aci318_14.13_3_1_1.bearing_pressure_service.md`). 13.3.1.1 gives the method, not a value:
the permissible pressure is the engineer's basis value, never a code number.
Units: kPa for pressures; the statics' units as in `aci318_14._footing`.
Errors: none of its own; a failed precondition gives `NEEDS_ENGINEER` (gaps G-1, G-2) through the core runner.
"""

from enum import StrEnum
from typing import Any

from eng_contract.cited import Cited
from eng_contract.params import eng_param
from eng_contract.verdicts import SubjectKind
from structural_codes.applicability import Outcome, Precondition
from structural_codes.check import check
from structural_codes.inputs import bounded
from structural_codes.meta import CheckMeta, GapDecl
from structural_codes.trace import TraceRecorder

from aci318_14._footing import COMPRESSION, ServiceFooting, full_contact

__all__ = ["ALLOWABLE_GROSS", "AllowableKind", "BearingInputs", "bearing_pressure_service"]

_CHECK_ID = "aci318_14.13_3_1_1.bearing_pressure_service"
_BASIS = frozenset({"basis.design_basis/1"})
_CAPACITY = Cited(value=0, unit="kPa", source="Mechanics of materials: a pressure capacity is positive")


class AllowableKind(StrEnum):
    """Kind of the permissible pressure of the design basis field `foundation.allowable_bearing_kind`."""

    GROSS = "gross"
    NET = "net"


class BearingInputs(ServiceFooting):
    """Service inputs of FS S1 to S5 plus the permissible pressure and its kind from the design basis (spec §3)."""

    q_allow_kPa: float = bounded(  # noqa: N815  # B-272: the unit suffix is fixed by the contract (EC §4.7.2)
        gt=_CAPACITY, unit="kPa", ref_capable=True, ref_kinds=_BASIS, engineering_quantity=True
    )
    allowable_kind: AllowableKind = eng_param(ref_capable=True, ref_kinds=_BASIS)


def _gross(inp: Any, t: TraceRecorder) -> bool:
    return bool(inp.allowable_kind is AllowableKind.GROSS)


ALLOWABLE_GROSS = Precondition(
    "ALLOWABLE_GROSS",
    Outcome.NEEDS_ENGINEER,
    "13.3.1.1",
    "allowable_kind must be gross; a net allowable pressure is gap G-2, not implemented",
    _gross,
)

META = CheckMeta(
    check_id=_CHECK_ID,
    pack="aci318_14",
    code="ACI 318-14",
    edition="2014",
    clauses=("13.3.1.1",),
    title="Service soil pressure under an isolated footing against the permissible pressure",
    members=frozenset({SubjectKind.FOOTING}),
    spec=f"aci318_14/{_CHECK_ID}.md",
    gaps=(
        GapDecl(id="G-1", clause="13.3.1.1", reason="partial soil contact (q_min < 0) is not implemented"),
        GapDecl(id="G-2", clause="13.3.1.1", reason="a net allowable pressure is not implemented"),
    ),
    assumptions=(
        "rigid footing with linear soil pressure (FS S4, S5)",
        "column centered on the footing",
        "the load case is a service (unfactored) case chosen by the caller (13.3.1.1)",
        "soil above the footing acts over the full plan area",
    ),
)


@check(meta=META, inputs=BearingInputs, preconditions=(ALLOWABLE_GROSS, COMPRESSION, full_contact("G-1")))
def bearing_pressure_service(inp: BearingInputs, t: TraceRecorder) -> None:
    """Compare `q_max_kPa` (FS S5, recorded by `COMPRESSION`) with `q_allow_kPa` (spec §4.2 steps 2 and 3)."""
    t.verdict(demand="q_max_kPa", capacity="q_allow_kPa")
