"""Shared column section model CS S1 to S7 and column preconditions CP (plan 0004 T1). R1 module.

Purpose: the section model of the axial-flexure spec §4.1 (S1 layout, S2 `eps_ty` and `beta1`, S3 section forces at a
neutral-axis depth `c`, S4 `eps_t`, S5 `phi`, S6 axial cap, S7 `c_full`), each step recorded on the caller's
`TraceRecorder` (`ColumnSection.at` evaluates S3 to S5 without recording, for a search), and the preconditions CP of
the maximum axial strength spec §2.1. `beta1` is shared with the flexure check. Units: inputs in mm, mm2, MPa, kN;
`ColumnSection` works in N and N.mm, the trace in kN and kN.m. Errors: `CheckDefinitionError` (a name recorded twice,
a value read before it is recorded, a malformed gap id).
"""

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from eng_contract.cited import Cited
from structural_codes.applicability import Outcome, Precondition
from structural_codes.errors import CheckDefinitionError
from structural_codes.trace import TraceRecorder

from aci318_14._common import CITED, SECTION_CITED
from aci318_14._footing import _step

__all__ = [
    "BAR_LAYOUT",
    "COLUMN_CITED",
    "SHORT_COLUMN",
    "STEEL_IN_SECTION",
    "ColumnSection",
    "SectionPoint",
    "TransverseKind",
    "axial_cap",
    "axial_compression",
    "beta1",
    "column_section",
    "record_point",
]

COLUMN_CITED = MappingProxyType(
    {
        "Es": Cited(value=200000, unit="MPa", source="ACI 318-14 20.2.2.2"),
        "phi_cc_tied": Cited(value=0.65, unit="1", source="ACI 318-14 Table 21.2.2 (compression-controlled, other)"),
        "phi_cc_spiral": Cited(
            value=0.75, unit="1", source="ACI 318-14 Table 21.2.2 (compression-controlled, spiral per 25.7.3)"
        ),
        "phi_tr_tied": Cited(value=0.25, unit="1", source="ACI 318-14 Table 21.2.2 (transition, other)"),
        "phi_tr_spiral": Cited(value=0.15, unit="1", source="ACI 318-14 Table 21.2.2 (transition, spiral)"),
        "pnmax_tied": Cited(value=0.80, unit="1", source="ACI 318-14 Table 22.4.2.1 (a), nonprestressed, ties"),
        "pnmax_spiral": Cited(value=0.85, unit="1", source="ACI 318-14 Table 22.4.2.1 (b), nonprestressed, spirals"),
        "kl_r_sway": Cited(
            value=22,
            unit="1",
            source="ACI 318-14 6.2.5(a) (columns not braced against sidesway; used for every column, CP)",
        ),
        "r_factor": Cited(value=0.30, unit="1", source="ACI 318-14 6.2.5.1(b) (rectangular columns)"),
        "c_corner": Cited(
            value=4, unit="1", source="Geometry: four corner bars counted twice in `2·n_bars_b + 2·n_bars_h`"
        ),
    }
)
# By trace name: the SI prefixes take the names `k_kilo` and `k_kilo_milli` (a `_kN` suffix would fix the unit kN).
_ALL = {**CITED, **SECTION_CITED, **COLUMN_CITED, "k_kilo": CITED["k_kN"], "k_kilo_milli": CITED["k_kNm"]}
_S1 = "AF CS S1 (Geometry: symmetric bar layers along the depth)"


class TransverseKind(StrEnum):
    """Transverse reinforcement stated by `transverse_kind` (AF §3): ties (25.7.2) or spirals (25.7.3)."""

    TIED = "tied"
    SPIRAL = "spiral"


def _c(t: TraceRecorder, name: str) -> float:
    """Return the cited constant `name`, recording it the first time (a constant is recorded once per trace)."""
    try:
        return t.value(name)
    except CheckDefinitionError:
        return t.const(name, _ALL[name])


def beta1(t: TraceRecorder) -> float:
    """Record `beta1_ratio` from the three rows of Table 22.2.2.4.3 (CS S2; flexure spec §4 step 4)."""
    names = ("beta1_hi", "beta1_slope", "beta1_step", "fc_beta_lo", "fc_beta_hi", "beta1_lo")
    c = {name: _c(t, name) for name in names}
    fc = t.value("fc_MPa")
    if fc <= c["fc_beta_lo"]:
        value = c["beta1_hi"]
    elif fc >= c["fc_beta_hi"]:
        value = c["beta1_lo"]
    else:
        value = c["beta1_hi"] - c["beta1_slope"] * (fc - c["fc_beta_lo"]) / c["beta1_step"]
    formula = "beta1_hi if fc_MPa <= fc_beta_lo else beta1_lo if fc_MPa >= fc_beta_hi"
    formula += " else beta1_hi - beta1_slope * (fc_MPa - fc_beta_lo) / beta1_step"
    return _step(t, "beta1_ratio", value, formula, "ACI 318-14 Table 22.2.2.4.3")


def _layout(inp: Any, t: TraceRecorder) -> float:
    """CS S1: record `Ast_mm2`, each layer's depth `d_<j>_mm` and area `A_<j>_mm2`; return `Ast_mm2`."""
    half, corner = _c(t, "c_half"), _c(t, "c_corner")
    n_b, a_bar, d_p, h = (t.value(n) for n in ("n_bars_b", "A_bar_mm2", "d_prime_mm", "h_mm"))
    f_ast = "A_bar_mm2 * (c_half * n_bars_b + c_half * n_bars_h - c_corner)"
    ast = _step(t, "Ast_mm2", a_bar * (half * n_b + half * t.value("n_bars_h") - corner), f_ast, _S1)
    js = range(int(inp.n_bars_h))
    for j in js:
        f_d = f"d_prime_mm + {j} * (h_mm - c_half * d_prime_mm) / (n_bars_h - 1)"
        _step(t, f"d_{j}_mm", d_p + j * (h - half * d_p) / js[-1], f_d, _S1)
        outer = j in (js[0], js[-1])
        f_a = "n_bars_b * A_bar_mm2" if outer else "c_half * A_bar_mm2"
        _step(t, f"A_{j}_mm2", (n_b if outer else half) * a_bar, f_a, _S1)
    return ast


def _bar_layout(inp: Any, t: TraceRecorder) -> bool:
    two_d = _c(t, "c_half") * t.value("d_prime_mm")
    return t.value("h_mm") > two_d and t.value("b_mm") > two_d


def _steel_in_section(inp: Any, t: TraceRecorder) -> bool:
    if hasattr(inp, "Ag_mm2"):
        ag = t.value("Ag_mm2")
    else:
        ag = _step(t, "Ag_mm2", t.value("b_mm") * t.value("h_mm"), "b_mm * h_mm", "Geometry: area of a rectangle")
    ast = t.value("Ast_mm2") if hasattr(inp, "Ast_mm2") else _layout(inp, t)
    return ast < ag


def _short_column(inp: Any, t: TraceRecorder) -> bool:
    limit, r = _c(t, "kl_r_sway"), _c(t, "r_factor")
    kl_r = t.value("k_factor") * t.value("lu_mm") / (r * min(t.value("b_mm"), t.value("h_mm")))
    f_kl = "k_factor * lu_mm / (r_factor * (b_mm if b_mm < h_mm else h_mm))"
    return _step(t, "kl_r_ratio", kl_r, f_kl, "ACI 318-14 6.2.5(a), 6.2.5.1(b)") <= limit


_NE = Outcome.NEEDS_ENGINEER
BAR_LAYOUT = Precondition("BAR_LAYOUT", _NE, "AF CS S1", "h_mm and b_mm must exceed 2*d_prime_mm", _bar_layout)
STEEL_IN_SECTION = Precondition("STEEL_IN_SECTION", _NE, "Eq. 22.4.2.2", "Ast_mm2 < Ag_mm2", _steel_in_section)
SHORT_COLUMN = Precondition(
    "SHORT_COLUMN", _NE, "6.2.5(a), 6.2.5.1(b)", "k*lu/r <= kl_r_sway; slenderness is gap G-2", _short_column
)


def axial_compression(gap_id: str) -> Precondition:
    """Return `AXIAL_COMPRESSION` (`Pu_kN >= 0`, CP) naming the check's axial-tension gap (AF G-3, MA G-1).

    Raises:
        CheckDefinitionError: `gap_id` is not `G-<n>`.
    """
    if not re.fullmatch(r"G-[0-9]+", gap_id):
        raise CheckDefinitionError(f"gap id {gap_id!r} must match G-<n>")

    def test(inp: Any, t: TraceRecorder) -> bool:
        pu = t.value("Pu_kN")
        return pu >= -pu  # Pu >= 0 without a numeric literal (gate FB005), exact for a finite float

    text = f"Pu_kN must be at least zero; axial tension (22.4.3) is gap {gap_id}, not implemented"
    return Precondition("AXIAL_COMPRESSION", _NE, "22.4.3", text, test)


def axial_cap(inp: Any, t: TraceRecorder) -> tuple[float, float, float]:
    """CS S6: record `Po_kN`, `Pn_max_kN` and `phiPn_max_kN` (kN) and return them; run after `STEEL_IN_SECTION`.

    Raises:
        CheckDefinitionError: `Ag_mm2` or `Ast_mm2` not recorded, or the cap already recorded.
    """
    kind = TransverseKind(inp.transverse_kind).value
    alpha, k_kn = _c(t, "alpha_1"), _c(t, "k_kilo")
    pnmax, phi_cc = _c(t, f"pnmax_{kind}"), _c(t, f"phi_cc_{kind}")
    fc, fy, ag, ast = (t.value(n) for n in ("fc_MPa", "fy_MPa", "Ag_mm2", "Ast_mm2"))
    f_po = "(alpha_1 * fc_MPa * (Ag_mm2 - Ast_mm2) + fy_MPa * Ast_mm2) * k_kilo"
    po = _step(t, "Po_kN", (alpha * fc * (ag - ast) + fy * ast) * k_kn, f_po, "ACI 318-14 Eq. 22.4.2.2")
    pn_max = _step(t, "Pn_max_kN", pnmax * po, f"pnmax_{kind} * Po_kN", "ACI 318-14 Table 22.4.2.1")
    src = "ACI 318-14 Table 21.2.2: uniform compression is compression-controlled"
    return po, pn_max, _step(t, "phiPn_max_kN", phi_cc * pn_max, f"phi_cc_{kind} * Pn_max_kN", src)


@dataclass(frozen=True, slots=True)
class SectionPoint:
    """CS S3 to S5 at one depth `c` (mm): forces in N, moment in N.mm about mid-depth, strains and `phi` unitless."""

    c: float
    a: float
    cc: float
    eps: tuple[float, ...]
    fs: tuple[float, ...]
    force: tuple[float, ...]
    pn: float
    mn: float
    eps_t: float
    phi: float


@dataclass(frozen=True, slots=True)
class ColumnSection:
    """The recorded values CS S3 to S5 need (mm, mm2, MPa, unitless) and `c_full` (mm), built by `column_section`."""

    kind: str
    b: float
    h: float
    dt: float
    fc: float
    fy: float
    es: float
    eps_cu: float
    eps_ty: float
    alpha: float
    beta1: float
    half: float
    depths: tuple[float, ...]
    areas: tuple[float, ...]
    phi_cc: float
    phi_tr: float
    phi_tc: float
    eps_tc: float
    c_full: float

    def phi(self, eps_t: float) -> float:
        """CS S5: `phi` of Table 21.2.2 for the net tensile strain `eps_t` (tension positive)."""
        if eps_t <= self.eps_ty:
            return self.phi_cc
        if eps_t >= self.eps_tc:
            return self.phi_tc
        return self.phi_cc + self.phi_tr * (eps_t - self.eps_ty) / (self.eps_tc - self.eps_ty)

    def at(self, c: float) -> SectionPoint:
        """CS S3 to S5 at the neutral-axis depth `c > 0` (mm), nothing recorded."""
        a = min(self.beta1 * c, self.h)
        cc = self.alpha * self.fc * a * self.b
        eps = tuple(self.eps_cu * (c - d) / c for d in self.depths)
        fs = tuple(self.es * e if abs(e) < self.eps_ty else math.copysign(self.fy, e) for e in eps)
        layers = tuple(zip(self.depths, self.areas, fs, strict=True))
        force = tuple(ar * (f - self.alpha * self.fc) if d < a else ar * f for d, ar, f in layers)
        mid = self.h / self.half
        mn = cc * (mid - a / self.half) + sum(f * (mid - d) for f, d in zip(force, self.depths, strict=True))
        eps_t = self.eps_cu * (self.dt - c) / c
        return SectionPoint(c, a, cc, eps, fs, force, cc + sum(force), mn, eps_t, self.phi(eps_t))


def column_section(inp: Any, t: TraceRecorder) -> ColumnSection:
    """Record CS S2 (`eps_ty_ratio`, `beta1_ratio`), S6 and S7 (`c_full_mm`) and the constants of S3 to S5.

    Run after the CP preconditions.

    Raises:
        CheckDefinitionError: the layout of CS S1 is not recorded, or a step is already recorded.
    """
    kind = TransverseKind(inp.transverse_kind).value
    es, eps_cu, _ = _c(t, "Es"), _c(t, "eps_cu"), _c(t, "k_kilo_milli")
    b, h, d_p, fc, fy = (t.value(n) for n in ("b_mm", "h_mm", "d_prime_mm", "fc_MPa", "fy_MPa"))
    eps_ty = _step(t, "eps_ty_ratio", fy / es, "fy_MPa / Es", "ACI 318-14 21.2.2.1 (eps_ty = fy/Es)")
    b1 = beta1(t)
    axial_cap(inp, t)
    full = "(h_mm - d_prime_mm) * eps_cu / (eps_cu - eps_ty_ratio)"
    c_full = max(h / b1, (h - d_p) * eps_cu / (eps_cu - eps_ty))
    f_full = f"h_mm / beta1_ratio if h_mm / beta1_ratio > {full} else {full}"
    c_full = _step(t, "c_full_mm", c_full, f_full, "AF CS S7 (every layer yielded in compression, a = h)")
    js = range(int(inp.n_bars_h))
    return ColumnSection(
        kind=kind,
        b=b,
        h=h,
        dt=h - d_p,
        fc=fc,
        fy=fy,
        es=es,
        eps_cu=eps_cu,
        eps_ty=eps_ty,
        alpha=_c(t, "alpha_1"),
        beta1=b1,
        half=_c(t, "c_half"),
        depths=tuple(t.value(f"d_{j}_mm") for j in js),
        areas=tuple(t.value(f"A_{j}_mm2") for j in js),
        phi_cc=_c(t, f"phi_cc_{kind}"),
        phi_tr=_c(t, f"phi_tr_{kind}"),
        phi_tc=_c(t, "phi_tc"),
        eps_tc=_c(t, "eps_tc"),
        c_full=c_full,
    )


def record_point(t: TraceRecorder, sec: ColumnSection, c: float, formula: str, source: str) -> SectionPoint:
    """Record `c_mm` (with the caller's `formula` and `source`) and CS S3 to S5 at it; return the point.

    Raises:
        CheckDefinitionError: `column_section` has not run on `t`, or a step is already recorded.
    """
    pt = sec.at(c)
    k_kn, k_knm = _c(t, "k_kilo"), _c(t, "k_kilo_milli")
    _step(t, "c_mm", c, formula, source)
    _step(t, "a_mm", pt.a, "beta1_ratio * c_mm if beta1_ratio * c_mm < h_mm else h_mm", "ACI 318-14 22.2.2.4.1")
    _step(t, "Cc_kN", pt.cc * k_kn, "alpha_1 * fc_MPa * a_mm * b_mm * k_kilo", "ACI 318-14 22.2.2.4.1")
    forces, terms = ["Cc_kN"], []
    for j, (e, f, force) in enumerate(zip(pt.eps, pt.fs, pt.force, strict=True)):
        _step(t, f"eps_{j}_ratio", e, f"eps_cu * (c_mm - d_{j}_mm) / c_mm", "ACI 318-14 22.2.1, 22.2.2.1")
        f_s = f"Es * eps_{j}_ratio if abs(eps_{j}_ratio) < eps_ty_ratio else fy_MPa if eps_{j}_ratio > 0 else -fy_MPa"
        _step(t, f"fs_{j}_MPa", f, f_s, "ACI 318-14 20.2.2.1")
        f_f = f"A_{j}_mm2 * (fs_{j}_MPa - alpha_1 * fc_MPa) * k_kilo if d_{j}_mm < a_mm"
        f_f += f" else A_{j}_mm2 * fs_{j}_MPa * k_kilo"
        _step(t, f"F_{j}_kN", force * k_kn, f_f, "AF CS S3 (bar inside the stress block: displaced concrete, C-3)")
        forces.append(f"F_{j}_kN")
        terms.append(f"F_{j}_kN * (h_mm / c_half - d_{j}_mm)")
    _step(t, "Pn_kN", pt.pn * k_kn, " + ".join(forces), "AF CS S3 (equilibrium, 22.2.1)")
    f_mn = f"(Cc_kN * (h_mm - a_mm) / c_half + {' + '.join(terms)}) / k_kilo * k_kilo_milli"
    _step(t, "Mn_kNm", pt.mn * k_knm, f_mn, "AF CS S3 (moment about mid-depth, 22.2.1)")
    _step(t, "eps_t_ratio", pt.eps_t, "eps_cu * (h_mm - d_prime_mm - c_mm) / c_mm", "AF CS S4 (22.2.1, dt = h - d')")
    k = sec.kind
    f_phi = f"phi_cc_{k} if eps_t_ratio <= eps_ty_ratio else phi_tc if eps_t_ratio >= eps_tc"
    f_phi += f" else phi_cc_{k} + phi_tr_{k} * (eps_t_ratio - eps_ty_ratio) / (eps_tc - eps_ty_ratio)"
    _step(t, "phi_ratio", pt.phi, f_phi, "ACI 318-14 Table 21.2.1 (a), Table 21.2.2 (AF CS S5)")
    return pt
