"""Check `aci318_14.25_4_2_3.development_length_bottom_bars`: straight bottom-bar anchorage of a footing. R1.

Purpose: per plan direction, the straight length of the bottom bars beyond the critical section at the column face
(13.2.7.1) against the tension development length of eq. 25.4.2.3a (SI) with `Ktr = 0` and the 25.4.2.1 floor
(clause spec, plan 0002 T8). Two verdicts, X then Y. Units: mm and MPa inputs; lengths in mm; `sf` in MPa^0.5
recorded with unit null (plan §6 Q6). Errors: none of its own; a failed precondition gives `NEEDS_ENGINEER` (gaps
G-1 and G-2 of the clause spec).
"""

# ruff: noqa: N815  # B-277: field names are fixed by the contract's unit suffixes (EC §4.7.2), e.g. fc_MPa

import math
import re
from enum import StrEnum
from typing import Any

from eng_contract.cited import Cited
from eng_contract.verdicts import SubjectKind
from structural_codes.applicability import Outcome, Precondition
from structural_codes.check import check
from structural_codes.inputs import CheckInputs, bounded
from structural_codes.meta import CheckMeta, GapDecl
from structural_codes.trace import TraceRecorder

from aci318_14._common import FC_MIN, FY_MAX, NORMALWEIGHT, ConcreteClass, const

__all__ = ["ANCHORAGE_POSITIVE", "UNCOATED", "Coating", "DevelopmentLengthInputs", "development_length_bottom_bars"]

_T = "ACI 318-14 Table 25.4.2.4"
_TE, _CB, _SF = "ACI 318-14 25.4.2.4", "ACI 318-14 25.4.2.3", "ACI 318-14 25.4.1.4"
_LOCAL = {
    "c_ld": Cited(value=1.1, unit="1", source="ACI 318-14 eq. 25.4.2.3a (SI), coefficient in MPa^0.5"),
    "conf_max": Cited(value=2.5, unit="1", source="ACI 318-14 25.4.2.3 (limit on (cb + Ktr)/db)"),
    "Ktr": Cited(value=0, unit="mm", source="ACI 318-14 25.4.2.3 (Ktr = 0 permitted as a design simplification)"),
    "ld_min": Cited(value=300, unit="mm", source="ACI 318-14 25.4.2.1(b)"),
    "psi_t_bottom": Cited(
        value=1.0, unit="1", source="ACI 318-14 Table 25.4.2.4 (casting position, other than top bars)"
    ),
    "psi_e_uncoated": Cited(value=1.0, unit="1", source="ACI 318-14 Table 25.4.2.4 (uncoated reinforcement)"),
    "psi_s_used": Cited(
        value=1.0, unit="1", source="ACI 318-14 Table 25.4.2.4 (No. 22 and larger row, used for all sizes, plan Q10)"
    ),
    "psi_te_max": Cited(value=1.7, unit="1", source="ACI 318-14 25.4.2.4 (limit on the product psi_t*psi_e)"),
}
_HALF = Cited(value=2, unit="1", source="Geometry: bar center at db/2; half spacing s/2; column face at c/2")
_LENGTH = Cited(value=0, unit="mm", source="Geometry: the length of a solid is positive")
_COVER = Cited(value=0, unit="mm", source="Geometry: a cover is not negative")
_STRENGTH = Cited(value=0, unit="MPa", source="Mechanics of materials: a strength is positive")
_CLAUSE = "25.4.2.3"
_ASSUMPTIONS = (
    "straight deformed bars without hooks; no reduction for excess reinforcement",
    "bottom bars: psi_t for bars other than top bars (Table 25.4.2.4)",
    "Ktr = 0 (25.4.2.3)",
    "psi_s = 1.0 for every bar size: metric sizes do not map to ASTM designations (conservative, plan Q10)",
    "critical section at the column face (13.2.7.1); column centered on the footing",
    "FC_MIN uses the general row of Table 19.2.1.1: Seismic Design Category A, B or C (C-3, plan Q16)",
)
# Per direction: suffix, span, column, bar diameter, spacing, side cover.
_DIRECTIONS = (
    ("x", "Lx_mm", "cx_mm", "db_x_mm", "s_x_mm", "cover_x_mm"),
    ("y", "Ly_mm", "cy_mm", "db_y_mm", "s_y_mm", "cover_y_mm"),
)


class Coating(StrEnum):
    """Bar coating of the design basis field `materials.rebar_coating` (Table 25.4.2.4)."""

    UNCOATED = "uncoated"
    EPOXY = "epoxy"
    ZINC_EPOXY_DUAL = "zinc_epoxy_dual"


class DevelopmentLengthInputs(CheckInputs):
    """Footing plan, column size, bars per direction, covers and materials (clause spec §3)."""

    Lx_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    Ly_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    cx_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    cy_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    db_x_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    db_y_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    s_x_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    s_y_mm: float = bounded(gt=_LENGTH, unit="mm", ref_capable=True)
    cover_x_mm: float = bounded(ge=_COVER, unit="mm", ref_capable=True, engineering_quantity=True)
    cover_y_mm: float = bounded(ge=_COVER, unit="mm", ref_capable=True, engineering_quantity=True)
    end_cover_mm: float = bounded(ge=_COVER, unit="mm", ref_capable=True, engineering_quantity=True)
    fc_MPa: float = bounded(gt=_STRENGTH, unit="MPa", ref_capable=True, engineering_quantity=True)
    fy_MPa: float = bounded(gt=_STRENGTH, unit="MPa", ref_capable=True, engineering_quantity=True)
    concrete_class: ConcreteClass
    coating: Coating


def _uncoated(inp: Any, t: TraceRecorder) -> bool:
    return bool(inp.coating == Coating.UNCOATED)


def _anchorage(inp: Any, t: TraceRecorder) -> bool:
    """Record `la = L/2 - c/2 - end_cover` per direction (clause spec §4 step 1); True when both are positive."""
    half, end = t.const("c_half", _HALF), t.value("end_cover_mm")
    ok = True
    for s, span, col, *_bars in _DIRECTIONS:
        la = t.step(
            f"la_{s}_mm",
            t.value(span) / half - t.value(col) / half - end,
            unit="mm",
            formula=f"{span}/c_half - {col}/c_half - end_cover_mm",
            source="ACI 318-14 13.2.7.1: critical section at the column face; straight length to the bar end",
            uses=[span, "c_half", col, "end_cover_mm"],
        )
        ok = ok and la > -la  # la > 0 without a numeric literal (gate FB005), exact for a finite float
    return ok


_NE = Outcome.NEEDS_ENGINEER
UNCOATED = Precondition("UNCOATED", _NE, "Table 25.4.2.4", "bars must be uncoated (gap G-2)", _uncoated)
ANCHORAGE_POSITIVE = Precondition(
    "ANCHORAGE_POSITIVE", _NE, "13.2.7.1", "la_x_mm > 0 and la_y_mm > 0: bar ends must pass the column face", _anchorage
)

_META = CheckMeta(
    check_id="aci318_14.25_4_2_3.development_length_bottom_bars",
    pack="aci318_14",
    code="ACI 318-14",
    edition="2014",
    clauses=(_CLAUSE, "25.4.2.1", "25.4.2.4", "25.4.1.4", "13.2.7.1", "19.2.1.1", "19.2.4.2", "20.2.2.4"),
    title="Development length of straight bottom bars of an isolated footing beyond the column face",
    members=frozenset({SubjectKind.FOOTING}),
    spec="aci318_14/aci318_14.25_4_2_3.development_length_bottom_bars.md",
    gaps=(
        GapDecl(id="G-1", clause="19.2.4.2", reason="lambda for lightweight concrete is not implemented"),
        GapDecl(id="G-2", clause="Table 25.4.2.4", reason="psi_e for coated bars is not implemented"),
    ),
    assumptions=_ASSUMPTIONS,
)


def _st(t: TraceRecorder, name: str, value: float, unit: str | None, formula: str, source: str) -> float:
    """Record a step whose `uses` are the recorded names in `formula`, in order (functions and literals skipped)."""
    words = re.findall(r"[A-Za-z_]\w*", formula.split("[")[0])
    uses = [w for w in dict.fromkeys(words) if w not in {"min", "max", "sqrt"}]
    return t.step(name, value, unit=unit, formula=formula, source=source, uses=uses)


@check(
    meta=_META,
    inputs=DevelopmentLengthInputs,
    preconditions=(NORMALWEIGHT, FC_MIN, FY_MAX, UNCOATED, ANCHORAGE_POSITIVE),
)
def development_length_bottom_bars(inp: DevelopmentLengthInputs, t: TraceRecorder) -> None:
    """Record `sf`, the factors, `cb`, the confinement term, `ld_eq` and `ld` per direction, and two verdicts.

    Clause spec §4 steps 2 to 7; `la_x_mm` and `la_y_mm` are recorded by `ANCHORAGE_POSITIVE` (step 1).
    """
    c = {name: t.const(name, cited) for name, cited in _LOCAL.items()}
    lam, cap, half, fy = const(t, "lambda_nw"), const(t, "sf_max"), t.value("c_half"), t.value("fy_MPa")
    sf = _st(t, "sf", min(math.sqrt(t.value("fc_MPa")), cap), None, "min(sqrt(fc_MPa), sf_max) [MPa^0.5]", _SF)
    psi_t = _st(t, "psi_t", c["psi_t_bottom"], "1", "psi_t_bottom", _T)
    psi_e = _st(t, "psi_e", c["psi_e_uncoated"], "1", "psi_e_uncoated", _T)
    # Recorded as psi_s_ratio: the bare name psi_s ends in the time suffix _s, which fixes the unit s (core AC10).
    psi_s = _st(t, "psi_s_ratio", c["psi_s_used"], "1", "psi_s_used", _T)
    psi_te = _st(t, "psi_te", min(psi_t * psi_e, c["psi_te_max"]), "1", "min(psi_t * psi_e, psi_te_max)", _TE)
    for s, _span, _col, bar, sp, cover in _DIRECTIONS:
        db = t.value(bar)
        f_cb = f"min({cover} + {bar} / c_half, {sp} / c_half)"
        cb = _st(t, f"cb_{s}_mm", min(t.value(cover) + db / half, t.value(sp) / half), "mm", f_cb, f"{_CB} (cb)")
        f_conf = f"min((cb_{s}_mm + Ktr) / {bar}, conf_max)"
        conf = _st(t, f"conf_{s}_ratio", min((cb + c["Ktr"]) / db, c["conf_max"]), "1", f_conf, _CB)
        ld_eq = fy / (c["c_ld"] * lam * sf) * (psi_te * psi_s / conf) * db
        f_ld = f"fy_MPa / (c_ld * lambda_nw * sf) * (psi_te * psi_s_ratio / conf_{s}_ratio) * {bar}"
        _st(t, f"ld_eq_{s}_mm", ld_eq, "mm", f_ld, "ACI 318-14 eq. 25.4.2.3a (SI)")
        _st(t, f"ld_{s}_mm", max(ld_eq, c["ld_min"]), "mm", f"max(ld_eq_{s}_mm, ld_min)", "ACI 318-14 25.4.2.1")
    for s, *_rest in _DIRECTIONS:
        t.verdict(demand=f"ld_{s}_mm", capacity=f"la_{s}_mm", clause=_CLAUSE, assumptions=_ASSUMPTIONS)
