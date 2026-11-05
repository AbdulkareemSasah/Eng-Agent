"""Check `aci318_14.22_6_5_2.punching_shear`: two-way shear of an isolated footing (clause spec, plan 0002 T5). R1.

Purpose: the factored shear stress on the critical perimeter at `d/2` from the column faces against `phi*vc`, with `vc`
the least of the three SI expressions of Table 22.6.5.2 (no shear reinforcement, interior column). Concentric shear
only: a non-zero base moment raises gap G-4 (8.4.4.2). One verdict per evaluation.
Units: mm, kN, kN.m and MPa inputs; stresses in MPa; `sf` in MPa^0.5 recorded with unit null (plan §6 Q6).
Errors: none of its own; a failed precondition or gap G-4 gives `NEEDS_ENGINEER` (gaps G-1 to G-4 of the clause spec).
"""

# ruff: noqa: N815  # B-274: field names are fixed by the contract's unit suffixes (EC §4.7.2), e.g. fc_MPa

import math
from typing import Any

from eng_contract.cited import Cited
from eng_contract.verdicts import SubjectKind
from structural_codes.applicability import Outcome, Precondition
from structural_codes.check import check
from structural_codes.errors import NotImplementedGap
from structural_codes.inputs import bounded
from structural_codes.meta import CheckMeta, GapDecl
from structural_codes.trace import TraceRecorder

from aci318_14._common import CITED, FC_MIN, NORMALWEIGHT, ConcreteClass, const
from aci318_14._footing import COMPRESSION, FootingLoads, full_contact

__all__ = ["PERIMETER_INSIDE", "PunchingShearInputs", "punching_shear"]

_TABLE = "ACI 318-14 Table 22.6.5.2"
_LOCAL = {
    "c_a": Cited(value=0.33, unit="1", source=f"{_TABLE} (a), coefficient in MPa^0.5"),
    "c_b": Cited(value=0.17, unit="1", source=f"{_TABLE} (b), coefficient in MPa^0.5"),
    "c_b2": Cited(value=2, unit="1", source=f"{_TABLE} (b), the term 2/beta"),
    "c_c": Cited(value=0.083, unit="1", source=f"{_TABLE} (c), coefficient in MPa^0.5"),
    "c_c2": Cited(value=2, unit="1", source=f"{_TABLE} (c), the term 2 + alphas*d/bo"),
    "alphas": Cited(value=40, unit="1", source="ACI 318-14 22.6.5.3 (interior columns)"),
    "c_perim": Cited(value=2, unit="1", source="Geometry: perimeter of a rectangle, 2*(b1 + b2)"),
}
_LENGTH = Cited(value=0, unit="mm", source="Geometry: the length of a solid is positive")
_STRENGTH = Cited(value=0, unit="MPa", source="Mechanics of materials: a strength is positive")
_CLAUSE = "22.6.5.2"
_ASSUMPTIONS = (
    "no shear reinforcement (22.6.1)",
    "rectangular column centered on the footing; rigid footing with a linear soil pressure (FS)",
    "d is the single effective depth chosen by the caller for the two-way section (plan Q5)",
    "net factored pressure from the column load only; footing and soil weights balance their own pressure (Q4)",
    "the subject's case is a factored (strength) case",
    "FC_MIN uses the general row of Table 19.2.1.1: Seismic Design Category A, B or C (C-1, plan Q16)",
)


class PunchingShearInputs(FootingLoads):
    """Factored reactions, footing plan, column size, effective depth and concrete (clause spec §3)."""

    cx_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    cy_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    d_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    fc_MPa: float = bounded(gt=_STRENGTH, unit="MPa", ref_capable=True, engineering_quantity=True)
    concrete_class: ConcreteClass


def _inside(inp: Any, t: TraceRecorder) -> bool:
    d = t.value("d_mm")
    return t.value("cx_mm") + d <= t.value("Lx_mm") and t.value("cy_mm") + d <= t.value("Ly_mm")


PERIMETER_INSIDE = Precondition(
    "PERIMETER_INSIDE",
    Outcome.NEEDS_ENGINEER,
    "22.6.5.3",
    "cx_mm + d_mm <= Lx_mm and cy_mm + d_mm <= Ly_mm; a perimeter reaching an edge is gap G-3, not implemented",
    _inside,
)

_META = CheckMeta(
    check_id="aci318_14.22_6_5_2.punching_shear",
    pack="aci318_14",
    code="ACI 318-14",
    edition="2014",
    clauses=(_CLAUSE, "22.6.1", "22.6.4.1", "22.6.5.3", "22.6.3.1", "13.3.3.1", "21.2.1", "19.2.1.1", "19.2.4.2"),
    title="Punching (two-way) shear of an isolated footing, concentric shear only",
    members=frozenset({SubjectKind.FOOTING}),
    spec="aci318_14/aci318_14.22_6_5_2.punching_shear.md",
    gaps=(
        GapDecl(id="G-1", clause="19.2.4.2", reason="lambda for lightweight concrete is not implemented"),
        GapDecl(id="G-2", clause="FS S5", reason="partial soil contact under factored loads is not implemented"),
        GapDecl(id="G-3", clause="22.6.5.3", reason="a critical perimeter reaching a footing edge is not implemented"),
        GapDecl(id="G-4", clause="8.4.4.2", reason="shear stress from moment transfer is not implemented"),
    ),
    assumptions=_ASSUMPTIONS,
)


def _step(t: TraceRecorder, name: str, value: float, unit: str | None, formula: str, source: str) -> float:
    """Record a step whose `uses` are the recorded names that appear in `formula`, in order."""
    names = formula.replace("(", " ").replace(")", " ").replace(",", " ").split()
    uses = [n for n in dict.fromkeys(names) if n[:1].isalpha() and n not in {"min", "max", "sqrt"}]
    return t.step(name, value, unit=unit, formula=formula, source=source, uses=uses)


@check(
    meta=_META,
    inputs=PunchingShearInputs,
    preconditions=(NORMALWEIGHT, FC_MIN, COMPRESSION, full_contact("G-2"), PERIMETER_INSIDE),
)
def punching_shear(inp: PunchingShearInputs, t: TraceRecorder) -> None:
    """Record the perimeter, `Vu`, `vu`, `sf`, `beta`, the three `vc`, `phivc` and one verdict (clause spec §4).

    Raises:
        NotImplementedGap: G-4 when `Mbx_kNm` or `Mby_kNm` is not exactly zero (no threshold is invented).
    """
    if t.value("Mbx_kNm") or t.value("Mby_kNm"):
        raise NotImplementedGap("G-4", "8.4.4.2", "base moment present: eccentric shear (moment transfer) is gap G-4")
    phi, lam, cap = const(t, "phi_v"), const(t, "lambda_nw"), const(t, "sf_max")
    # The shared k_kN cannot be recorded under its own name: the suffix _kN would fix the unit kN (core AC10).
    k_kn = t.const("k_kilo", CITED["k_kN"])
    c = {name: t.const(name, cited) for name, cited in _LOCAL.items()}
    d, cx, cy = t.value("d_mm"), t.value("cx_mm"), t.value("cy_mm")
    perimeter = "ACI 318-14 22.6.4.1: critical section at d/2 from the column faces"
    b1 = _step(t, "b1_mm", cx + d, "mm", "cx_mm + d_mm", perimeter)
    b2 = _step(t, "b2_mm", cy + d, "mm", "cy_mm + d_mm", perimeter)
    bo = _step(t, "bo_mm", c["c_perim"] * (b1 + b2), "mm", "c_perim * ( b1_mm + b2_mm )", perimeter)
    a = t.value("A_mm2")
    shear = "ACI 318-14 13.3.3.1 and 22.6.1: column load less the uniform factored pressure inside the perimeter"
    f_vu = "FZ_kN * ( A_mm2 - b1_mm * b2_mm ) / A_mm2"
    vu_kn = _step(t, "Vu_kN", t.value("FZ_kN") * (a - b1 * b2) / a, "kN", f_vu, shear)
    _step(
        t, "vu_MPa", vu_kn / k_kn / (bo * d), "MPa", "Vu_kN / k_kilo / ( bo_mm * d_mm )", "Statics: stress = V/(bo*d)"
    )
    sf = _step(
        t, "sf", min(math.sqrt(t.value("fc_MPa")), cap), None, "min( sqrt( fc_MPa ), sf_max )", "ACI 318-14 22.6.3.1"
    )
    beta = _step(t, "beta_ratio", max(cx, cy) / min(cx, cy), "1", "max( cx_mm, cy_mm ) / min( cx_mm, cy_mm )", _TABLE)
    va = _step(t, "vc_a_MPa", c["c_a"] * lam * sf, "MPa", "c_a * lambda_nw * sf", f"{_TABLE} (a)")
    f_b = "c_b * ( 1 + c_b2 / beta_ratio ) * lambda_nw * sf"
    vb = _step(t, "vc_b_MPa", c["c_b"] * (beta + c["c_b2"]) / beta * lam * sf, "MPa", f_b, f"{_TABLE} (b)")
    f_c = "c_c * ( c_c2 + alphas * d_mm / bo_mm ) * lambda_nw * sf"
    vcc = _step(t, "vc_c_MPa", c["c_c"] * (c["c_c2"] + c["alphas"] * d / bo) * lam * sf, "MPa", f_c, f"{_TABLE} (c)")
    vc, label = min(zip((va, vb, vcc), ("(a)", "(b)", "(c)"), strict=True))
    _step(t, "vc_MPa", vc, "MPa", "min( vc_a_MPa, vc_b_MPa, vc_c_MPa )", _TABLE)
    t.note(f"governing: Table 22.6.5.2 {label}")
    _step(t, "phivc_MPa", phi * vc, "MPa", "phi_v * vc_MPa", "ACI 318-14 Table 21.2.1(b)")
    t.verdict(demand="vu_MPa", capacity="phivc_MPa", clause=_CLAUSE, assumptions=_ASSUMPTIONS)
