"""Check `aci318_14.22_4_2_1.max_axial_strength`: design axial strength of a short column (plan 0004 T2). R1.

Purpose: per plan direction, the factored axial compression against `phi*Pn_max` from Eq. 22.4.2.2 and Table 22.4.2.1
with the compression-controlled strength reduction factor of Table 21.2.2. One verdict. Units: mm, mm2, MPa, kN.
Errors: none of its own; a failed precondition or gap gives `NEEDS_ENGINEER`.
"""

# ruff: noqa: N815  # B-331: field names are fixed by the contract's unit suffixes (EC §4.7.2), e.g. Ast_mm2

from eng_contract.cited import Cited
from eng_contract.verdicts import SubjectKind
from structural_codes.check import check
from structural_codes.inputs import CheckInputs, bounded, unbounded
from structural_codes.meta import CheckMeta, GapDecl
from structural_codes.trace import TraceRecorder

from aci318_14._column import (
    SHORT_COLUMN,
    STEEL_IN_SECTION,
    TransverseKind,
    axial_cap,
    axial_compression,
)
from aci318_14._common import FC_MIN, FY_MAX
from aci318_14._footing import _step

__all__ = ["MaxAxialInputs", "max_axial_strength"]

_LENGTH = Cited(value=0, unit="mm", source="Geometry: the length of a solid is positive")
_AREA = Cited(value=0, unit="mm2", source="Geometry: a provided bar area is positive")
_STRENGTH = Cited(value=0, unit="MPa", source="Mechanics of materials: a strength is positive")
_ONE = Cited(value=0, unit="1", source="Geometry: a factor or count is positive")
_CLAUSE = "22.4.2.1"
_ASSUMPTIONS = (
    "nonprestressed column; transverse reinforcement conforms to 25.7.2 or 25.7.3 as stated by transverse_kind",
    "not part of a special seismic system (FY_MAX general row, plan Q10)",
    "the subject's case is a factored (strength) case",
    "FC_MIN uses the general row of Table 19.2.1.1: Seismic Design Category A, B or C (C-2, plan Q16)",
    "effective length factor k is taken from the input without a default (plan Q5)",
)


class MaxAxialInputs(CheckInputs):
    """Factored axial force, section, reinforcement, materials and slenderness inputs (clause spec §3)."""

    Pu_kN: float = unbounded(reason="signed axial force, compression positive", unit="kN")
    b_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    h_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    Ast_mm2: float = bounded(gt=_AREA, unit="mm2", ref_capable=True)
    fc_MPa: float = bounded(gt=_STRENGTH, unit="MPa", ref_capable=True, engineering_quantity=True)
    fy_MPa: float = bounded(gt=_STRENGTH, unit="MPa", ref_capable=True, engineering_quantity=True)
    transverse_kind: TransverseKind
    k_factor: float = bounded(gt=_ONE, unit="1", ref_capable=True)
    lu_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)


_META = CheckMeta(
    check_id="aci318_14.22_4_2_1.max_axial_strength",
    pack="aci318_14",
    code="ACI 318-14",
    edition="2014",
    clauses=(
        _CLAUSE,
        "22.4.2.2",
        "Table 22.4.2.1",
        "10.5.1.1",
        "21.2.1",
        "21.2.2",
        "6.2.5",
        "6.2.5.1",
        "19.2.1.1",
        "20.2.2.4",
    ),
    title="Maximum axial strength of a short, nonprestressed column",
    members=frozenset({SubjectKind.FRAME}),
    spec="aci318_14/aci318_14.22_4_2_1.max_axial_strength.md",
    gaps=(
        GapDecl(id="G-1", clause="22.4.3", reason="axial tension is not implemented"),
        GapDecl(id="G-2", clause="6.6", reason="slenderness effects beyond the SHORT_COLUMN limit"),
    ),
    assumptions=_ASSUMPTIONS,
)


@check(
    meta=_META,
    inputs=MaxAxialInputs,
    preconditions=(FC_MIN, FY_MAX, STEEL_IN_SECTION, SHORT_COLUMN, axial_compression("G-1")),
)
def max_axial_strength(inp: MaxAxialInputs, t: TraceRecorder) -> None:
    """Record `Ag`, `Po`, `Pn_max`, `phi_ratio`, `phiPn_max` and one verdict (clause spec §4)."""
    kind = TransverseKind(inp.transverse_kind).value
    axial_cap(inp, t)
    phi = t.value("phiPn_max_kN") / t.value("Pn_max_kN")
    src = "ACI 318-14 Table 21.2.2: uniform compression is compression-controlled"
    _step(t, "phi_ratio", phi, f"phi_cc_{kind}", src)
    t.verdict(demand="Pu_kN", capacity="phiPn_max_kN", clause=_CLAUSE, assumptions=_ASSUMPTIONS)
