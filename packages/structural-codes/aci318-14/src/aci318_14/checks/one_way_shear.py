"""Check `aci318_14.22_5_5_1.one_way_shear`: one-way shear of an isolated footing (clause spec, plan 0002 T4). R1.

Purpose: per plan direction, the factored shear beyond the section at `d` from the column face (FS S4 integral) against
`phi*Vc` with `Vc = 0.17*lambda*sf*bw*d` (eq. 22.5.5.1, SI), no shear reinforcement. Two verdicts, X then Y.
Units: mm, kN, kN.m, MPa and kPa inputs; shears in kN; `sf` in MPa^0.5 recorded with unit null (plan §6 Q6).
Errors: none of its own; a failed precondition gives `NEEDS_ENGINEER` (gaps G-1 and G-2 of the clause spec).
"""

# ruff: noqa: N815  # B-273: field names are fixed by the contract's unit suffixes (EC §4.7.2), e.g. fc_MPa

import math

from eng_contract.cited import Cited
from eng_contract.verdicts import SubjectKind
from structural_codes.check import check
from structural_codes.inputs import bounded
from structural_codes.meta import CheckMeta, GapDecl
from structural_codes.trace import TraceRecorder

from aci318_14._common import CITED, FC_MIN, NORMALWEIGHT, ConcreteClass, const
from aci318_14._footing import COMPRESSION, FootingLoads, full_contact, one_way_shears

__all__ = ["OneWayShearInputs", "one_way_shear"]

_C_VC = Cited(value=0.17, unit="1", source="ACI 318-14 eq. 22.5.5.1 (SI), coefficient in MPa^0.5")
_LENGTH = Cited(value=0, unit="mm", source="Geometry: the length of a solid is positive")
_STRENGTH = Cited(value=0, unit="MPa", source="Mechanics of materials: a strength is positive")
_CLAUSE = "22.5.5.1"
_ASSUMPTIONS = (
    "no shear reinforcement: Vn = Vc + Vs with Vs = 0 (eq. 22.5.1.1)",
    "column centered on the footing; rigid footing with a linear soil pressure (FS)",
    "net factored pressure from the column load only; footing and soil weights balance their own pressure (Q4)",
    "the subject's case is a factored (strength) case",
    "FC_MIN uses the general row of Table 19.2.1.1: Seismic Design Category A, B or C (C-2, plan Q16)",
)
# Per direction: suffix, width bw, effective depth.
_DIRECTIONS = (("x", "Ly_mm", "d_x_mm"), ("y", "Lx_mm", "d_y_mm"))


class OneWayShearInputs(FootingLoads):
    """Factored reactions, footing plan, column size, effective depths and concrete (clause spec §3)."""

    cx_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    cy_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    d_x_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    d_y_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    fc_MPa: float = bounded(gt=_STRENGTH, unit="MPa", ref_capable=True, engineering_quantity=True)
    concrete_class: ConcreteClass


_META = CheckMeta(
    check_id="aci318_14.22_5_5_1.one_way_shear",
    pack="aci318_14",
    code="ACI 318-14",
    edition="2014",
    clauses=(_CLAUSE, "22.5.1.1", "22.5.3.1", "13.3.3.1", "13.2.7.2", "21.2.1", "19.2.1.1", "19.2.4.2"),
    title="One-way shear of an isolated footing at d from the column face",
    members=frozenset({SubjectKind.FOOTING}),
    spec="aci318_14/aci318_14.22_5_5_1.one_way_shear.md",
    gaps=(
        GapDecl(id="G-1", clause="Table 19.2.4.2", reason="lambda for lightweight concrete is not implemented"),
        GapDecl(id="G-2", clause="FS S5", reason="partial soil contact under factored loads is not implemented"),
    ),
    assumptions=_ASSUMPTIONS,
)


@check(meta=_META, inputs=OneWayShearInputs, preconditions=(NORMALWEIGHT, FC_MIN, COMPRESSION, full_contact("G-2")))
def one_way_shear(inp: OneWayShearInputs, t: TraceRecorder) -> None:
    """Record `Vu`, `sf`, `Vc` and `phiVc` per direction and one verdict each, X then Y (clause spec §4 steps 2-7)."""
    one_way_shears(t)
    phi, lam, cap = const(t, "phi_v"), const(t, "lambda_nw"), const(t, "sf_max")
    # The shared k_kN cannot be recorded under its own name: the suffix _kN would fix the unit kN (core AC10).
    k_kn = t.const("k_kilo", CITED["k_kN"])
    c_vc = t.const("c_vc", _C_VC)
    sf = t.step(
        "sf",
        min(math.sqrt(t.value("fc_MPa")), cap),
        unit=None,
        formula="min(sqrt(fc_MPa), sf_max) [MPa^0.5]",
        source="ACI 318-14 22.5.3.1",
        uses=["fc_MPa", "sf_max"],
    )
    for s, width, depth in _DIRECTIONS:
        vc = t.step(
            f"Vc_{s}_kN",
            c_vc * lam * sf * t.value(width) * t.value(depth) * k_kn,
            unit="kN",
            formula=f"c_vc * lambda_nw * sf * {width} * {depth} * k_kilo",
            source="ACI 318-14 eq. 22.5.5.1 (SI), bw = footing width",
            uses=["c_vc", "lambda_nw", "sf", width, depth, "k_kilo"],
        )
        t.step(
            f"phiVc_{s}_kN",
            phi * vc,
            unit="kN",
            formula=f"phi_v * Vc_{s}_kN",
            source="ACI 318-14 Table 21.2.1(b); eq. 22.5.1.1 with Vs = 0",
            uses=["phi_v", f"Vc_{s}_kN"],
        )
    for s, _width, _depth in _DIRECTIONS:
        t.verdict(demand=f"Vu_{s}_kN", capacity=f"phiVc_{s}_kN", clause=_CLAUSE, assumptions=_ASSUMPTIONS)
