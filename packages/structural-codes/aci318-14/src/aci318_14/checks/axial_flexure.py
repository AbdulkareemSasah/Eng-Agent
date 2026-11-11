"""Check `aci318_14.22_4_1_1.axial_flexure_uniaxial`: axial force with uniaxial flexure (plan 0004 T3). R1.

Purpose: find the design strength on the demand ray of the P-M interaction diagram (strain compatibility, CS S1 to S7)
and compare `Mu` with the capped moment. Uniaxial bending only; biaxial, tension and slender columns are gaps.
Units: mm, mm2, MPa, kN, kN.m inputs; section forces in N and N.mm inside the search.
Errors: `NotImplementedGap` G-4 when the demand-ray bracket is not unique on the grid.
"""

# ruff: noqa: N815  # B-332: field names are fixed by the contract's unit suffixes (EC §4.7.2)

import itertools
from collections.abc import Callable

from eng_contract.cited import Cited
from eng_contract.verdicts import SubjectKind
from structural_codes.applicability import Outcome, Precondition
from structural_codes.check import check
from structural_codes.errors import NotImplementedGap
from structural_codes.inputs import CheckInputs, bounded, unbounded
from structural_codes.meta import CheckMeta, GapDecl
from structural_codes.trace import TraceRecorder

from aci318_14._column import (
    BAR_LAYOUT,
    SHORT_COLUMN,
    STEEL_IN_SECTION,
    ColumnSection,
    SectionPoint,
    TransverseKind,
    axial_compression,
    column_section,
    record_point,
)
from aci318_14._common import CITED, FC_MIN, FY_MAX
from aci318_14._footing import _step

__all__ = ["AxialFlexureInputs", "axial_flexure_uniaxial", "bracket_demand_ray", "demand_ray_g"]

_LENGTH = Cited(value=0, unit="mm", source="Geometry: the length of a solid is positive")
_AREA = Cited(value=0, unit="mm2", source="Geometry: a provided bar area is positive")
_STRENGTH = Cited(value=0, unit="MPa", source="Mechanics of materials: a strength is positive")
_COUNT = Cited(value=0, unit="1", source="Geometry: a bar count is at least two per face")
_CLAUSE = "22.4.1.1"
_ASSUMPTIONS = (
    "nonprestressed column; rectangular section bent about the axis parallel to b",
    "symmetric bar arrangement (CS S1); transverse reinforcement as stated, not checked here (plan §6 Q4)",
    "not part of a special seismic system (FY_MAX); FC_MIN uses the general row of Table 19.2.1.1",
    "short column: k*lu/r <= kl_r_sway; effective length factor k from the design basis (plan §6 Q5)",
    "compression-positive Pu_kN and moment magnitudes converted by the caller (plan §6 Q2)",
)
_G4_CLAUSE = "AF §4.2 step 3"
_G4_SRC = "Numerical method: bracketing grid of AF §4.2 step 3"
_S5 = "AF §4.2 step 5 (capped design moment on the demand ray)"


def _flexure_present(_inp: AxialFlexureInputs, t: TraceRecorder) -> bool:
    return t.value("Mu_kNm") > -t.value("Mu_kNm")


def _uniaxial(_inp: AxialFlexureInputs, t: TraceRecorder) -> bool:
    return t.value("Mu_other_kNm") <= -t.value("Mu_other_kNm")


_FLEXURE_PRESENT = Precondition(
    "FLEXURE_PRESENT",
    Outcome.NOT_APPLICABLE,
    "22.4.2.1",
    "Mu_kNm must be positive; pure axial load is the maximum axial strength check",
    _flexure_present,
)
_UNIAXIAL = Precondition(
    "UNIAXIAL",
    Outcome.NEEDS_ENGINEER,
    "22.4.1.1",
    "Mu_other_kNm must be zero; biaxial bending is gap G-1",
    _uniaxial,
)


class AxialFlexureInputs(CheckInputs):
    """Factored axial force and moments, section layout and materials (AF spec §3)."""

    Pu_kN: float = unbounded(reason="signed axial force, compression positive", unit="kN", ref_capable=True)
    Mu_kNm: float = bounded(ge=Cited(value=0, unit="kN.m", source="Geometry: moment magnitude"), unit="kN.m")
    Mu_other_kNm: float = bounded(
        ge=Cited(value=0, unit="kN.m", source="Geometry: moment magnitude"), unit="kN.m", ref_capable=True
    )
    b_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    h_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    d_prime_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    n_bars_b: int = bounded(ge=_COUNT, unit="1", ref_capable=True)
    n_bars_h: int = bounded(ge=_COUNT, unit="1", ref_capable=True)
    A_bar_mm2: float = bounded(gt=_AREA, unit="mm2", ref_capable=True)
    fc_MPa: float = bounded(gt=_STRENGTH, unit="MPa", ref_capable=True, engineering_quantity=True)
    fy_MPa: float = bounded(gt=_STRENGTH, unit="MPa", ref_capable=True, engineering_quantity=True)
    transverse_kind: TransverseKind = TransverseKind.TIED
    k_factor: float = bounded(gt=_COUNT, unit="1", ref_capable=True)
    lu_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)


_META = CheckMeta(
    check_id="aci318_14.22_4_1_1.axial_flexure_uniaxial",
    pack="aci318_14",
    code="ACI 318-14",
    edition="2014",
    clauses=(
        _CLAUSE,
        "10.5.1.1",
        "22.2.1",
        "22.2.2.1",
        "22.2.2.4.1",
        "21.2.2",
        "22.4.2.2",
        "6.2.5",
    ),
    title="Axial force with uniaxial flexure on a short rectangular column",
    members=frozenset({SubjectKind.FRAME}),
    spec="aci318_14/aci318_14.22_4_1_1.axial_flexure_uniaxial.md",
    gaps=(
        GapDecl(id="G-1", clause="22.4.1.1", reason="biaxial bending: no cited normative method"),
        GapDecl(id="G-2", clause="6.2.5", reason="slenderness beyond kl_r_sway"),
        GapDecl(id="G-3", clause="22.4.3", reason="axial tension with flexure"),
        GapDecl(id="G-4", clause=_G4_CLAUSE, reason="demand ray does not bracket uniquely on the grid"),
    ),
    assumptions=_ASSUMPTIONS,
)


def demand_ray_g(sec: ColumnSection, c: float, pu_n: float, mu_nmm: float) -> float:
    """AF §4.2 step 2: `g(c) = Mu*Pn(c) - Pu*Mn(c)` with forces in N and N.mm (nothing recorded)."""
    pt = sec.at(c)
    return mu_nmm * pt.pn - pu_n * pt.mn


def bracket_demand_ray(
    c_full: float,
    n_grid: int,
    g: Callable[[float], float],
    *,
    two: float,
    one: float,
) -> tuple[float, float]:
    """AF §4.2 step 3: bracket the root on `c in (0, c_full]`; raise G-4 when the grid is ambiguous.

    `two` and `one` are the cited factors `c_half` and `c_half/c_half` (FB005: no numeric literals here).

    Raises:
        NotImplementedGap: G-4 when `g(c_1) >= 0`, up-crossings are not exactly one, or a down-crossing exists.
    """
    one_i, two_i = int(one), int(two)
    if n_grid < two_i:
        raise NotImplementedGap("G-4", clause=_G4_CLAUSE, reason="n_grid must be at least c_half")
    g1 = g(c_full / n_grid)
    if g1 >= -g1:
        raise NotImplementedGap("G-4", clause=_G4_CLAUSE, reason="g(c_1) >= 0 on the bracketing grid")
    zero = one - one
    up = down = int(zero)
    lo = hi = c_full / n_grid
    prev_c, prev_g = lo, g1
    for i in range(two_i, n_grid + one_i):
        c_i = c_full * i / n_grid
        g_i = g(c_i)
        if prev_g < -prev_g and g_i >= -g_i:
            up += one_i
            lo, hi = prev_c, c_i
        if prev_g >= -prev_g and g_i < -g_i:
            down += one_i
        prev_c, prev_g = c_i, g_i
    if up != one_i or down != int(zero):
        reason = f"crossings_up = {up}, crossings_down = {down} on the bracketing grid"
        raise NotImplementedGap("G-4", clause=_G4_CLAUSE, reason=reason)
    return lo, hi


def _bisect(lo: float, hi: float, g: Callable[[float], float], *, two: float) -> tuple[float, float]:
    """AF §4.2 step 4: bisect `[lo, hi]` with `g(lo) < 0 <= g(hi)` to float64 resolution."""
    while True:
        m = (lo + hi) / two
        if m in (lo, hi):
            break
        if g(m) < -g(m):
            lo = m
        else:
            hi = m
    return lo, hi


def _cap_m_knm(
    pt: SectionPoint, pu_kn: float, mu_knm: float, phi_pn_max_kn: float, k_kn: float, k_knm: float
) -> tuple[float, float, float, bool]:
    """AF §4.2 step 5: capped design moment on the demand ray (nothing recorded)."""
    phi_pn = pt.phi * pt.pn * k_kn
    phi_mn = pt.phi * pt.mn * k_knm
    on_cap = pu_kn > -pu_kn and phi_pn > phi_pn_max_kn
    cap_m = mu_knm * phi_pn_max_kn / pu_kn if on_cap else phi_mn
    return cap_m, phi_pn, phi_mn, on_cap


def _count_crossings(
    c_full: float, n_grid: int, g: Callable[[float], float], *, one: float, two: float
) -> tuple[int, int]:
    one_i = int(one)
    g_vals = [g(c_full * i / n_grid) for i in range(one_i, n_grid + one_i)]
    up = down = int(one - one)
    for a, b in itertools.pairwise(g_vals):
        if a < -a and b >= -b:
            up += one_i
        if a >= -a and b < -b:
            down += one_i
    return up, down


@check(
    meta=_META,
    inputs=AxialFlexureInputs,
    preconditions=(
        FC_MIN,
        FY_MAX,
        BAR_LAYOUT,
        STEEL_IN_SECTION,
        SHORT_COLUMN,
        axial_compression("G-3"),
        _FLEXURE_PRESENT,
        _UNIAXIAL,
    ),
)
def axial_flexure_uniaxial(inp: AxialFlexureInputs, t: TraceRecorder) -> None:
    """Record the interaction root search and one verdict: demand `Mu_kNm`, capacity `capM_kNm` (§4.2).

    Raises:
        NotImplementedGap: G-4 from `bracket_demand_ray` when the grid does not bracket the ray uniquely.
    """
    k_kn = t.const("k_kilo", CITED["k_kN"])
    k_knm = t.const("k_kilo_milli", CITED["k_kNm"])
    pu_kn, mu_knm = t.value("Pu_kN"), t.value("Mu_kNm")
    pu_n, mu_nmm = pu_kn / k_kn, mu_knm / k_knm
    sec = column_section(inp, t)
    n_grid = int(
        t.const(
            "n_grid",
            Cited(
                value=1000,
                unit="1",
                source=(
                    "Numerical method: bracketing grid of AF clause spec §4.2 step 3 (not an engineering value; C-5)"
                ),
            ),
        )
    )
    phi_pn_max = t.value("phiPn_max_kN")
    c_full = sec.c_full
    two = t.value("c_half")
    one = two / two

    def g(c: float) -> float:
        return demand_ray_g(sec, c, pu_n, mu_nmm)

    def _crossings(up: int, down: int) -> None:
        f_up = "up-crossings on the bracketing grid"
        t.step("crossings_up", float(up), unit=None, formula=f_up, source=_G4_SRC, uses=["n_grid", "c_full_mm"])
        f_down = "down-crossings on the bracketing grid"
        t.step("crossings_down", float(down), unit=None, formula=f_down, source=_G4_SRC, uses=["n_grid", "c_full_mm"])

    try:
        lo, hi = bracket_demand_ray(c_full, n_grid, g, two=two, one=one)
    except NotImplementedGap as exc:
        _crossings(*_count_crossings(c_full, n_grid, g, one=one, two=two))
        raise exc
    _crossings(*_count_crossings(c_full, n_grid, g, one=one, two=two))
    grid_uses = ["c_full_mm", "n_grid"]
    t.step("c_lo_mm", lo, unit="mm", formula="c_full_mm * i / n_grid", source=_G4_SRC, uses=grid_uses)
    t.step("c_hi_mm", hi, unit="mm", formula="c_full_mm * (i + 1) / n_grid", source=_G4_SRC, uses=grid_uses)
    lo, hi = _bisect(lo, hi, g, two=two)
    pt_lo, pt_hi = sec.at(lo), sec.at(hi)
    cap_lo, _, _, _ = _cap_m_knm(pt_lo, pu_kn, mu_knm, phi_pn_max, k_kn, k_knm)
    cap_hi, _, _, _ = _cap_m_knm(pt_hi, pu_kn, mu_knm, phi_pn_max, k_kn, k_knm)
    t.step("capM_lo_kNm", cap_lo, unit="kN.m", formula="capped moment at c_lo_mm", source=_S5, uses=["c_lo_mm"])
    t.step("capM_hi_kNm", cap_hi, unit="kN.m", formula="capped moment at c_hi_mm", source=_S5, uses=["c_hi_mm"])
    chosen_c = lo if cap_lo <= cap_hi else hi
    c_formula = "c_lo_mm if capM_lo_kNm <= capM_hi_kNm else c_hi_mm"
    record_point(t, sec, chosen_c, c_formula, _G4_SRC)
    pt = sec.at(chosen_c)
    cap_m, phi_pn, phi_mn, on_cap = _cap_m_knm(pt, pu_kn, mu_knm, phi_pn_max, k_kn, k_knm)
    _step(t, "phiPn_kN", phi_pn, "phi_ratio * Pn_kN", "ACI 318-14 Table 21.2.1 (a), Table 21.2.2")
    _step(t, "phiMn_kNm", phi_mn, "phi_ratio * Mn_kNm", "ACI 318-14 Table 21.2.1 (a), Table 21.2.2")
    t.step(
        "on_cap",
        on_cap,
        unit=None,
        formula="phiPn_kN > phiPn_max_kN and Pu_kN > 0",
        source="AF §4.2 step 5 (ray meets the axial cap)",
        uses=["phiPn_kN", "phiPn_max_kN", "Pu_kN"],
    )
    f_cap = "Mu_kNm * phiPn_max_kN / Pu_kN" if on_cap else "phiMn_kNm"
    _step(t, "capM_kNm", cap_m, f_cap, _S5)
    t.verdict(demand="Mu_kNm", capacity="capM_kNm", clause=_CLAUSE, assumptions=_ASSUMPTIONS)
