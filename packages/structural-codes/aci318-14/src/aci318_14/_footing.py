"""Shared footing statics FS S1 to S5 (bearing spec §4.1), their preconditions and two exact integrals. R1 module.

Purpose: S1 to S5, `COMPRESSION`, `full_contact(gap)` and the S4 integrals of the one-way shear and flexure specs
(§4), each step recorded on the caller's `TraceRecorder`. Units: inputs in mm, kN, kN.m, kN/m3, kPa; lengths go to m
through `k_m`; a step's unit is its suffix's (EC §4.7.2). Errors: `CheckDefinitionError` (statics missing or run
twice, malformed gap id).
"""

# ruff: noqa: N815  # B-271: field names are fixed by the contract's unit suffixes (EC §4.7.2), e.g. gamma_c_kN_m3

import re
from typing import Any

from eng_contract.cited import Cited
from eng_contract.units import kind_for_field
from structural_codes.applicability import Outcome, Precondition
from structural_codes.errors import CheckDefinitionError
from structural_codes.inputs import CheckInputs, bounded, unbounded
from structural_codes.trace import TraceRecorder

from aci318_14._common import const

__all__ = ["COMPRESSION", "FootingLoads", "ServiceFooting", "face_moments", "full_contact", "one_way_shears", "statics"]

_LENGTH = Cited(value=0, unit="mm", source="Geometry: the length of a solid is positive")
_DEPTH = Cited(value=0, unit="mm", source="Geometry: a height or depth is not negative")
_DENSITY = Cited(value=0, unit="kN/m3", source="Mechanics of materials: a weight density is positive")
_SURCHARGE = Cited(value=0, unit="kPa", source="Statics: a downward surcharge is not negative")
_SIGNED = "signed reaction component in global axes; no physical bound (plan 0002 §6 Q1)"
_S1 = "FS S1 (Mechanics of materials: rectangle about its centroid)"
_S2 = "FS S2 (Statics: moment about the base centroid of -F acting at the reaction height)"
_S3 = "FS S3 (Statics: vertical load on the soil)"
_S5 = "FS S5 (Statics: corner pressures of the linear field, full contact)"
_NOT_NAMES = frozenset({"abs", "if", "else", "Lp", "a"})
# Per direction: suffix, span, width, column, effective depth, moment about the other axis, its inertia.
_AXES = (
    ("x", "Lx_mm", "Ly_mm", "cx_mm", "d_x_mm", "Mby_kNm", "Iy_mm4"),
    ("y", "Ly_mm", "Lx_mm", "cy_mm", "d_y_mm", "Mbx_kNm", "Ix_mm4"),
)


class FootingLoads(CheckInputs):
    """Reactions of the support joint and the footing plan geometry (strength form of S3: `N = FZ`)."""

    FX_kN: float = unbounded(reason=_SIGNED, unit="kN", ref_capable=True, engineering_quantity=True)
    FY_kN: float = unbounded(reason=_SIGNED, unit="kN", ref_capable=True, engineering_quantity=True)
    FZ_kN: float = unbounded(reason=_SIGNED, unit="kN", ref_capable=True, engineering_quantity=True)
    MX_kNm: float = unbounded(reason=_SIGNED, unit="kN.m", ref_capable=True, engineering_quantity=True)
    MY_kNm: float = unbounded(reason=_SIGNED, unit="kN.m", ref_capable=True, engineering_quantity=True)
    Lx_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    Ly_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    reaction_height_mm: float = bounded(ge=_DEPTH, unit="mm", ref_capable=True)


class ServiceFooting(FootingLoads):
    """Adds the weights of the service form of S3: `N = FZ + W` (bearing spec §3)."""

    h_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    soil_depth_mm: float = bounded(ge=_DEPTH, unit="mm", ref_capable=True, engineering_quantity=True)
    gamma_c_kN_m3: float = bounded(gt=_DENSITY, unit="kN/m3", ref_capable=True, engineering_quantity=True)
    gamma_s_kN_m3: float = bounded(gt=_DENSITY, unit="kN/m3", ref_capable=True, engineering_quantity=True)
    surcharge_kPa: float = bounded(ge=_SURCHARGE, unit="kPa", ref_capable=True, engineering_quantity=True)


def _step(t: TraceRecorder, name: str, value: float, formula: str, source: str) -> float:
    """Record a step whose unit is its suffix's canonical unit and whose `uses` are the names in `formula`."""
    kind = kind_for_field(name)
    uses = [n for n in dict.fromkeys(re.findall(r"[A-Za-z_]\w*", formula)) if n not in _NOT_NAMES]
    unit = None if kind is None else kind.canonical_unit
    return t.step(name, value, unit=unit, formula=formula, source=source, uses=uses)


def statics(inp: FootingLoads, t: TraceRecorder) -> None:
    """Record S1, S2, S3 (service form for a `ServiceFooting`, else strength form, where `q_avg_kPa` is `q0`), S5.

    Raises:
        CheckDefinitionError: a step or constant is already recorded on `t`.
    """
    k, c_s, c_i = const(t, "k_m"), const(t, "c_S"), const(t, "c_I")
    lx, ly, e = t.value("Lx_mm"), t.value("Ly_mm"), t.value("reaction_height_mm") * k
    a = _step(t, "A_mm2", lx * ly, "Lx_mm * Ly_mm", _S1)
    sx = _step(t, "Sx_mm3", lx * ly * ly / c_s, "Lx_mm * Ly_mm^2 / c_S", _S1)
    sy = _step(t, "Sy_mm3", ly * lx * lx / c_s, "Ly_mm * Lx_mm^2 / c_S", _S1)
    _step(t, "Ix_mm4", lx * ly * ly * ly / c_i, "Lx_mm * Ly_mm^3 / c_I", _S1)
    _step(t, "Iy_mm4", ly * lx * lx * lx / c_i, "Ly_mm * Lx_mm^3 / c_I", _S1)
    mbx = _step(t, "Mbx_kNm", -t.value("MX_kNm") + e * t.value("FY_kN"), "-MX_kNm + reaction_height_mm*k_m*FY_kN", _S2)
    mby = _step(t, "Mby_kNm", -t.value("MY_kNm") - e * t.value("FX_kN"), "-MY_kNm - reaction_height_mm*k_m*FX_kN", _S2)
    a_m2, fz = a * k * k, t.value("FZ_kN")
    if isinstance(inp, ServiceFooting):
        own = inp.h_mm * k * inp.gamma_c_kN_m3 + inp.soil_depth_mm * k * inp.gamma_s_kN_m3
        w = a_m2 * own + a_m2 * inp.surcharge_kPa
        f_w = "A_mm2*k_m^2 * (h_mm*k_m*gamma_c_kN_m3 + soil_depth_mm*k_m*gamma_s_kN_m3) + A_mm2*k_m^2 * surcharge_kPa"
        _step(t, "W_kN", w, f_w, f"{_S3}, service form")
        n = _step(t, "N_kN", fz + w, "FZ_kN + W_kN", _S3)
    else:
        n = _step(t, "N_kN", fz, "FZ_kN", f"{_S3}, strength form")
    q_avg = _step(t, "q_avg_kPa", n / a_m2, "N_kN / (A_mm2 * k_m^2)", _S5)
    bend = abs(mbx) / (sx * k * k * k) + abs(mby) / (sy * k * k * k)
    q_bend = _step(t, "q_bend_kPa", bend, "abs(Mbx_kNm) / (Sx_mm3*k_m^3) + abs(Mby_kNm) / (Sy_mm3*k_m^3)", _S5)
    _step(t, "q_max_kPa", q_avg + q_bend, "q_avg_kPa + q_bend_kPa", _S5)
    _step(t, "q_min_kPa", q_avg - q_bend, "q_avg_kPa - q_bend_kPa", _S5)


def _compression(inp: FootingLoads, t: TraceRecorder) -> bool:
    statics(inp, t)
    n = t.value("N_kN")
    return n > -n  # n > 0 without a numeric literal (gate FB005), exact for a finite float


COMPRESSION = Precondition("COMPRESSION", Outcome.NEEDS_ENGINEER, "FS S3", "N_kN must be positive", _compression)


def full_contact(gap_id: str) -> Precondition:
    """Return `FULL_CONTACT` (`q_min_kPa >= 0`, FS S5) naming the partial-contact gap; declare it after COMPRESSION.

    Raises:
        CheckDefinitionError: `gap_id` is not `G-<n>`; at evaluation, the statics are not recorded.
    """
    if not re.fullmatch(r"G-[0-9]+", gap_id):
        raise CheckDefinitionError(f"gap id {gap_id!r} must match G-<n>")

    def test(inp: Any, t: TraceRecorder) -> bool:
        q_min = t.value("q_min_kPa")
        return q_min >= -q_min  # q_min >= 0 without a numeric literal, exact for a finite float

    text = f"q_min_kPa must be at least zero; partial soil contact is gap {gap_id}, not implemented"
    return Precondition("FULL_CONTACT", Outcome.NEEDS_ENGINEER, "FS S5", text, test)


def one_way_shears(t: TraceRecorder) -> tuple[float, float]:
    """Record the factored shear beyond the section at `d` from the column face, X then Y (one-way spec §4 2-3).

    `Lc = L/2 - c/2 - d`; `Vu = B*Lc*(q0 + |M|*xbar/I)`, `xbar = (c/2 + d + L/2)/2`, for `Lc > 0`, else 0 (E-1).

    Raises:
        CheckDefinitionError: the statics or the inputs `cx_mm`, `cy_mm`, `d_x_mm`, `d_y_mm` are not recorded.
    """
    half = const(t, "c_half")
    k, q0 = t.value("k_m"), t.value("q_avg_kPa")
    out = []
    for s, span, width, col, depth, moment, inertia in _AXES:
        length, c, d = t.value(span), t.value(col), t.value(depth)
        src = "ACI 318-14 13.2.7.2 with 13.3.3.1: section at d from the column face"
        lc = _step(t, f"Lc_{s}_mm", length / half - c / half - d, f"{span}/c_half - {col}/c_half - {depth}", src)
        f_x = f"({col}/c_half + {depth} + {span}/c_half) / c_half"
        xbar = _step(t, f"xbar_{s}_mm", (c / half + d + length / half) / half, f_x, "Geometry: centroid beyond it")
        slope = abs(t.value(moment)) / (t.value(inertia) * k * k * k * k)
        vu = t.value(width) * k * lc * k * (q0 + slope * xbar * k) if lc > -lc else lc - lc
        f_v = f"{width}*Lc_{s}_mm*k_m^2 * (q_avg_kPa + abs({moment})*xbar_{s}_mm*k_m / ({inertia}*k_m^4))"
        f_v += f" if Lc_{s}_mm > 0 else 0"
        out.append(_step(t, f"Vu_{s}_kN", vu, f_v, "FS S4 integrated beyond the section"))
    return out[0], out[1]


def face_moments(t: TraceRecorder) -> tuple[float, float]:
    """Record the factored moment about the column face, X then Y (flexure spec §4 steps 2-3).

    `Lp = L/2 - c/2`, `a = c/2`, `k = |M|/I`; `Mu = B*[q0*Lp^2/2 + k*(Lp^3/3 + a*Lp^2/2)]` for `Lp > 0`, else 0.

    Raises:
        CheckDefinitionError: the statics or the inputs `cx_mm`, `cy_mm` are not recorded.
    """
    half, third = const(t, "c_half"), const(t, "c_third")
    k, q0 = t.value("k_m"), t.value("q_avg_kPa")
    out = []
    for s, span, width, col, _depth, moment, inertia in _AXES:
        src = "ACI 318-14 13.2.7.1 (Table 13.2.7.1): section at the face of a concrete column"
        lp = _step(t, f"Lp_{s}_mm", t.value(span) / half - t.value(col) / half, f"{span}/c_half - {col}/c_half", src)
        lp_m, a_m = lp * k, t.value(col) / half * k
        slope = abs(t.value(moment)) / (t.value(inertia) * k * k * k * k)
        cubic = lp_m * lp_m * lp_m / third + a_m * lp_m * lp_m / half
        mu = t.value(width) * k * (q0 * lp_m * lp_m / half + slope * cubic) if lp > -lp else lp - lp
        f_m = f"{width}*k_m * (q_avg_kPa*Lp^2/c_half + abs({moment})/({inertia}*k_m^4)"
        f_m += f" * (Lp^3/c_third + a*Lp^2/c_half)); Lp = Lp_{s}_mm*k_m, a = {col}/c_half*k_m; 0 if Lp_{s}_mm <= 0"
        out.append(_step(t, f"Mu_{s}_kNm", mu, f_m, "FS S4 moment beyond the column face about it"))
    return out[0], out[1]
