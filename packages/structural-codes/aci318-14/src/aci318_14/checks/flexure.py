"""Check `aci318_14.13_2_7_1.flexure_at_column_face`: flexure of an isolated footing (clause spec, plan 0002 T6). R1.

Purpose: per plan direction, the factored moment of the soil pressure about the column face (FS S4 integral) against
`phi*Mn` of the bottom bars over the full width, rectangular stress block with yielding steel (22.2, 22.3.1.1).
Only tension-controlled sections (`eps_t >= eps_tc`, Table 21.2.2) are checked; otherwise gap G-2. Two verdicts, X
then Y. Units: mm, mm2, kN, kN.m, MPa and kPa inputs; moments in kN.m; strains and `beta1` unitless.
Errors: none of its own; a failed precondition or gap G-2 gives `NEEDS_ENGINEER` (gaps G-1 and G-2 of the spec).
"""

# ruff: noqa: N815  # B-275: field names are fixed by the contract's unit suffixes (EC §4.7.2), e.g. As_x_mm2

from eng_contract.cited import Cited
from eng_contract.verdicts import SubjectKind
from structural_codes.check import check
from structural_codes.errors import NotImplementedGap
from structural_codes.inputs import bounded
from structural_codes.meta import CheckMeta, GapDecl
from structural_codes.trace import TraceRecorder

from aci318_14._column import beta1 as _beta1
from aci318_14._common import CITED, FC_MIN, FY_MAX, const
from aci318_14._footing import COMPRESSION, FootingLoads, _step, face_moments, full_contact

__all__ = ["FlexureInputs", "flexure_at_column_face"]

_LENGTH = Cited(value=0, unit="mm", source="Geometry: the length of a solid is positive")
_AREA = Cited(value=0, unit="mm2", source="Geometry: a provided bar area is positive")
_STRENGTH = Cited(value=0, unit="MPa", source="Mechanics of materials: a strength is positive")
_CLAUSE = "13.2.7.1"
_ASSUMPTIONS = (
    "concrete column centered on the footing: critical section at its face (Table 13.2.7.1)",
    "one layer of bottom bars per direction with dt = d; reinforcement spread over the full width (band rule, Q7)",
    "net factored pressure from the column load only; footing and soil weights balance their own pressure (Q4)",
    "the footing is not part of a special seismic system (FY_MAX, plan Q8)",
    "the subject's case is a factored (strength) case",
    "FC_MIN uses the general row of Table 19.2.1.1: Seismic Design Category A, B or C (C-2, plan Q16)",
)
# Per direction: suffix, width b, effective depth, steel area.
_DIRECTIONS = (("x", "Ly_mm", "d_x_mm", "As_x_mm2"), ("y", "Lx_mm", "d_y_mm", "As_y_mm2"))


class FlexureInputs(FootingLoads):
    """Factored reactions, footing plan, column size, effective depths, bottom steel and materials (spec §3)."""

    cx_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    cy_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    d_x_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    d_y_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    As_x_mm2: float = bounded(gt=_AREA, unit="mm2", ref_capable=True)
    As_y_mm2: float = bounded(gt=_AREA, unit="mm2", ref_capable=True)
    fc_MPa: float = bounded(gt=_STRENGTH, unit="MPa", ref_capable=True, engineering_quantity=True)
    fy_MPa: float = bounded(gt=_STRENGTH, unit="MPa", ref_capable=True, engineering_quantity=True)


_META = CheckMeta(
    check_id="aci318_14.13_2_7_1.flexure_at_column_face",
    pack="aci318_14",
    code="ACI 318-14",
    edition="2014",
    clauses=(_CLAUSE, "13.3.3.1", "22.3.1.1", "22.2.2.1", "22.2.2.4.1", "22.2.2.4.3", "21.2.1", "21.2.2", "20.2.2.4"),
    title="Flexure of an isolated footing at the column face, tension-controlled sections",
    members=frozenset({SubjectKind.FOOTING}),
    spec="aci318_14/aci318_14.13_2_7_1.flexure_at_column_face.md",
    gaps=(
        GapDecl(id="G-1", clause="FS S5", reason="partial soil contact under factored loads is not implemented"),
        GapDecl(id="G-2", clause="21.2.2", reason="phi in the transition and compression-controlled ranges"),
    ),
    assumptions=_ASSUMPTIONS,
)


@check(meta=_META, inputs=FlexureInputs, preconditions=(FC_MIN, FY_MAX, COMPRESSION, full_contact("G-1")))
def flexure_at_column_face(inp: FlexureInputs, t: TraceRecorder) -> None:
    """Record `Mu`, `beta1`, `a`, `c`, `eps_t`, `Mn` and `phiMn` per direction and one verdict each, X then Y.

    Raises:
        NotImplementedGap: G-2 when `eps_t < eps_tc` in a direction (the section is not tension-controlled).
    """
    face_moments(t)
    phi, eps_tc, eps_cu, alpha = (const(t, n) for n in ("phi_tc", "eps_tc", "eps_cu", "alpha_1"))
    # The shared k_kNm cannot be recorded under its own name: the suffix _kNm would fix the unit kN.m (core AC10).
    k_knm, half = t.const("k_kilo_milli", CITED["k_kNm"]), t.value("c_half")
    beta1 = _beta1(t)
    fc, fy = t.value("fc_MPa"), t.value("fy_MPa")
    for s, width, depth, steel in _DIRECTIONS:
        a_s, d = t.value(steel), t.value(depth)
        f_a = f"{steel} * fy_MPa / (alpha_1 * fc_MPa * {width})"
        a = _step(t, f"a_{s}_mm", a_s * fy / (alpha * fc * t.value(width)), f_a, "ACI 318-14 22.2.2.4.1, b = width")
        c = _step(t, f"c_{s}_mm", a / beta1, f"a_{s}_mm / beta1_ratio", "ACI 318-14 22.2.2.4.1 (a = beta1*c)")
        f_e = f"eps_cu * ({depth} - c_{s}_mm) / c_{s}_mm"
        eps_t = _step(t, f"eps_t_{s}_ratio", eps_cu * (d - c) / c, f_e, "ACI 318-14 22.2.2.1, dt = d")
        if eps_t < eps_tc:
            reason = f"eps_t_{s}_ratio = {eps_t:.6f} < eps_tc: the section is not tension-controlled; gap G-2"
            raise NotImplementedGap("G-2", clause="21.2.2", reason=reason)
        f_m = f"{steel} * fy_MPa * ({depth} - a_{s}_mm / c_half) * k_kilo_milli"
        mn = _step(t, f"Mn_{s}_kNm", a_s * fy * (d - a / half) * k_knm, f_m, "ACI 318-14 22.3.1.1 with 22.2")
        src = "ACI 318-14 Table 21.2.1 (a) with Table 21.2.2, tension-controlled"
        _step(t, f"phiMn_{s}_kNm", phi * mn, f"phi_tc * Mn_{s}_kNm", src)
    for s, _width, _depth, _steel in _DIRECTIONS:
        t.verdict(demand=f"Mu_{s}_kNm", capacity=f"phiMn_{s}_kNm", clause=_CLAUSE, assumptions=_ASSUMPTIONS)
